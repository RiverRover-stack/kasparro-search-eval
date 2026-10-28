from sqlalchemy.orm import Session, sessionmaker

from backend.app.main import app, health


def test_health_checks_database(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        response = health(session)

    assert response.model_dump() == {"status": "ok", "database": "ok"}


def test_openapi_documents_dataset_import() -> None:
    schema = app.openapi()

    assert "/health" in schema["paths"]
    assert "/datasets" in schema["paths"]
    assert "/analyses" in schema["paths"]
    assert "/analyses/{analysis_id}" in schema["paths"]

