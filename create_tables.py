from app.database import engine
from app.models.base import Base

# Import models so SQLAlchemy knows them
from app.models.portal import Portal
from app.models.portal_connection import PortalConnection
from app.models.claim_summary import ClaimSummary


def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully")


if __name__ == "__main__":
    main()