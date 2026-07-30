FROM python:3.12-slim-trixie

RUN python -m pip install --no-cache-dir uv

WORKDIR /alive

COPY pyproject.toml uv.lock README.md ./

RUN ["uv", "sync", "--frozen", "--no-dev", "--no-install-project"]

COPY . .

EXPOSE 9010

VOLUME ["/alive/data"]

CMD ["/alive/.venv/bin/python", "main.py"]
