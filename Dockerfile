FROM python:3
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
RUN --mount=type=secret,id=_env,dst=./.env cat ./.env
CMD ["python3", "cryptoscanner.py"]