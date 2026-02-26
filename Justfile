# Synchronize dependencies
sync:
    #!/usr/bin/env bash
    cd backend && uv sync

# Format code with ruff
format-backend:
    #!/usr/bin/env bash
    cd backend && uv sync --quiet && uv run ruff format .

# Run the backend
run-backend:
    #!/usr/bin/env bash
    cd backend && uv sync --quiet && PYTHONPATH=src uv run python -m app.main
    
# Check the backend
check-backend:
    #!/usr/bin/env bash
    cd backend && uv sync --quiet && uv run ruff format --check .

run-frontend:
    cd frontend && npm run dev