import uvicorn

from app.core.settings import apisettings


def main():
    """
    Main function to run the FastAPI application.
    """

    uvicorn.run(
        "app.application:app",
        host=apisettings.host,
        port=apisettings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
