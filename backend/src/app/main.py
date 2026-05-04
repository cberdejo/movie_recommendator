import uvicorn

from app.core.settings import api_settings


def main():
    """
    Main function to run the FastAPI application.
    """

    uvicorn.run(
        "app.application:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
