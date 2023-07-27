FROM python:3
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
RUN --mount=type=secret,id=my_env,src=.env .\
  echo $TELEGRAM_TOKEN_SCANNER
CMD ["python3", "cryptoscanner.py"]