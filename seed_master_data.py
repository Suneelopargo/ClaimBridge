from app.database import SessionLocal
from app.models.portal import Portal
from app.models.portal_connection import PortalConnection


def main() -> None:
    db = SessionLocal()

    try:
        portal = (
            db.query(Portal)
            .filter(Portal.code == "IHX")
            .first()
        )

        if portal is None:
            portal = Portal(
                code="IHX",
                name="IHX Provider Portal",
                description="IHX portal for claim status tracking",
                base_url="https://provider.ihx.in",
                active=True,
            )
            db.add(portal)
            db.flush()

        connection = (
            db.query(PortalConnection)
            .filter(
                PortalConnection.portal_id == portal.id,
                PortalConnection.connection_name == "IHX - HCG",
            )
            .first()
        )

        if connection is None:
            connection = PortalConnection(
                portal_id=portal.id,
                connection_name="IHX - HCG",
                hospital_name="Healthcare Global Enterprises",
                environment="PROD",
                username="testpoc@solventek.com",
                encrypted_password=None,
                graph_mailbox="testpoc@solventek.com",
                auth_type="USERNAME_PASSWORD_OTP",
                active=True,
            )
            db.add(connection)

        db.commit()

        print(f"Portal ID: {portal.id}")
        print(f"Portal Connection ID: {connection.id}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()