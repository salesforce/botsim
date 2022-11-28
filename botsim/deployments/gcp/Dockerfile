FROM nvcr.io/nvidia/pytorch:20.12-py3



COPY requirements_gpu.txt requirements_gpu.txt

ENV DEBIAN_FRONTEND=noninteractive 

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    wget \
    build-essential \
    vim \
    htop \
    curl \
    git less ssh cmake \
    zip unzip gzip bzip2 \
    python3-tk gcc g++ libpq-dev


RUN pip install -U pip && pip install -r requirements_gpu.txt
RUN pip install torch==1.9.0+cu111 torchvision==0.10.0+cu111 torchaudio==0.9.0 -f https://download.pytorch.org/whl/torch_stable.html

COPY . /app
WORKDIR /app
ENV PYTHONPATH="${PYTHONPATH}:/app"
#ENV STORAGE="S3"
ENV DATABASE_URL="/app/db/botsim_sqlite_demo.db"

EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "/app/botsim/streamlit_app/app.py"]


