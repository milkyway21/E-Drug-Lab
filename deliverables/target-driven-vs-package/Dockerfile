FROM ghcr.io/mamba-org/micromamba:1.5.10

WORKDIR /workspace

USER root

ENV PATH=/opt/conda/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV WORKSPACE_DIR=/workspace
ENV PYTHONPATH=/workspace/code

RUN micromamba install -y -n base -c conda-forge \
        python=3.7 \
        biopython=1.79 \
        numpy=1.21.6 \
        pandas=1.3.5 \
        matplotlib=3.5.3 \
        rdkit=2022.03.5 \
        imbalanced-learn=0.7.0 \
        scikit-learn=1.0.2 \
        scipy=1.7.3 \
        seaborn=0.11.2 \
        pillow=9.2.0 \
    && micromamba clean -a -y \
    && /opt/conda/bin/python -m pip install --no-cache-dir \
        chembl_webresource_client==0.10.8 \
        fastapi==0.95.2 \
        uvicorn==0.22.0 \
        python-multipart==0.0.6

COPY code /workspace/code

RUN mkdir -p /workspace/data /workspace/models /workspace/data/results

EXPOSE 8000

CMD ["uvicorn", "app.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
