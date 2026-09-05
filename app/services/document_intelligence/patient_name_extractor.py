import base64
import json
import os
import re
from dataclasses import dataclass, asdict

from openai import OpenAI


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


@dataclass
class PatientNameCandidate:
    value: str
    normalized_value: str
    source: str
    confidence: float
    handwritten: bool
    evidence: str
    requires_review: bool = False


@dataclass
class PatientNameResolution:
    resolved_value: str
    confidence: float
    status: str
    candidates: list[PatientNameCandidate]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


HONORIFICS = {
    "MR",
    "MRS",
    "MS",
    "MISS",
    "DR",
    "MASTER",
    "SMT",
    "SMT.",
    "SHRI",
    "SRI",
}


def normalize_patient_name(value: str | None) -> str:
    if not value:
        return ""

    value = str(value).upper().strip()

    # Remove common Indian honorifics.
    for title in HONORIFICS:
        value = re.sub(
            rf"\b{re.escape(title)}\b",
            " ",
            value,
            flags=re.IGNORECASE,
        )

    # Keep only alphabetic characters.
    value = re.sub(r"[^A-Z]", "", value)

    return value


def _image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(
            image_file.read()
        ).decode("utf-8")


def _clean_json(content: str) -> dict:
    content = (content or "").strip()

    if content.startswith("```json"):
        content = content.replace("```json", "", 1)

    if content.startswith("```"):
        content = content.replace("```", "", 1)

    if content.endswith("```"):
        content = content[:-3]

    return json.loads(content.strip())


class PatientNameExtractor:

    def extract_from_image(
        self,
        image_path: str,
        expected_patient_name: str | None = None,
        document_type: str | None = None,
    ) -> PatientNameResolution:

        base64_image = _image_to_base64(image_path)

        expected_text = (
            expected_patient_name.strip()
            if expected_patient_name
            else ""
        )

        prompt = f"""
You are performing patient-name verification on ONE page from an
Indian hospital insurance claim packet.

This task is ONLY about identifying the patient's name.

The page may contain:
- handwritten text
- printed text
- stamps
- signatures
- hospital staff names
- doctor names
- proposer / insured names
- relative names
- payer names
- patient name

Document type:
{document_type or "UNKNOWN"}

Known packet-level patient name, if available:
{expected_text or "NOT AVAILABLE"}

IMPORTANT:

1. Inspect the image carefully, especially fields labelled:
   - Patient Name
   - Name of Patient
   - Patient
   - Insured Name
   - Member Name

2. Do NOT return a doctor's name, hospital employee name,
   relative name, proposer name or signature as the patient name.

3. Handwritten patient names are valid evidence.

4. Titles and honorifics such as:
   Mr, Mrs, Ms, Smt, Shri, Sri, Dr
   must NOT by themselves cause a mismatch.

Example:

"Mrs Mrunalini"
"Smt Mrunalini"
"Mrunalini"

may represent the same patient.

5. The known packet-level patient name is supporting context only.
   DO NOT copy it merely because it was provided.

6. If the handwriting is ambiguous, report the uncertainty.
   Do NOT invent characters merely to match the expected name.

7. If the visible name strongly resembles the expected patient
   name but one or more handwritten characters are uncertain,
   return the visible interpretation and lower the confidence.

8. If no patient-name field can reasonably be identified,
   return an empty patientName.

Return STRICT JSON only:

{{
  "patientName": "",
  "confidence": 0.0,
  "handwritten": false,
  "fieldLocated": false,
  "evidence": "",
  "reason": ""
}}
"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You verify patient identity evidence in "
                        "Indian healthcare claim documents. "
                        "Never force an uncertain handwritten name "
                        "to match an expected value."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    "data:image/png;base64,"
                                    f"{base64_image}"
                                )
                            },
                        },
                    ],
                },
            ],
            temperature=0,
        )

        try:
            result = _clean_json(
                response.choices[0].message.content
            )

            patient_name = str(
                result.get("patientName") or ""
            ).strip()

            try:
                confidence = float(
                    result.get("confidence") or 0
                )
            except (TypeError, ValueError):
                confidence = 0.0

            candidate = PatientNameCandidate(
                value=patient_name,
                normalized_value=normalize_patient_name(
                    patient_name
                ),
                source="SPECIALIZED_VISION",
                confidence=confidence,
                handwritten=bool(
                    result.get("handwritten", False)
                ),
                evidence=str(
                    result.get("evidence") or ""
                ),
                requires_review=confidence < 0.80,
            )

            expected_normalized = normalize_patient_name(
                expected_patient_name
            )

            extracted_normalized = (
                candidate.normalized_value
            )

            if not patient_name:
                return PatientNameResolution(
                    resolved_value="",
                    confidence=confidence,
                    status="NOT_FOUND",
                    candidates=[candidate],
                    reason=(
                        result.get("reason")
                        or "Patient name could not be identified"
                    ),
                )

            if (
                expected_normalized
                and extracted_normalized == expected_normalized
            ):
                return PatientNameResolution(
                    resolved_value=patient_name,
                    confidence=confidence,
                    status="MATCH",
                    candidates=[candidate],
                    reason=(
                        "Specialized image extraction matches "
                        "packet patient identity after normalization"
                    ),
                )

            if expected_normalized:
                return PatientNameResolution(
                    resolved_value=patient_name,
                    confidence=confidence,
                    status="REVIEW_REQUIRED",
                    candidates=[candidate],
                    reason=(
                        "Patient name was identified from the image "
                        "but does not exactly match packet identity "
                        "after normalization"
                    ),
                )

            return PatientNameResolution(
                resolved_value=patient_name,
                confidence=confidence,
                status="EXTRACTED",
                candidates=[candidate],
                reason=(
                    result.get("reason")
                    or "Patient name extracted from document image"
                ),
            )

        except Exception as exc:
            return PatientNameResolution(
                resolved_value="",
                confidence=0.0,
                status="EXTRACTION_ERROR",
                candidates=[],
                reason=str(exc),
            )