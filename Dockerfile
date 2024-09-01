FROM python:3.11
ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1
RUN pip install --upgrade pip
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY . .
CMD ["python3", "cryptoscanner.py"]