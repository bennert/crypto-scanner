FROM python:3
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
RUN --mount=type=secret,id=telegram_token_scanner \
  export "TELEGRAM_TOKEN_SCANNER=$(cat /run/secrets/TELEGRAM_TOKEN_SCANNER)" && \
  echo $TELEGRAM_TOKEN_SCANNER
CMD ["python3", "cryptoscanner.py"]