FROM python:3.13-slim
RUN useradd -m -u 1000 user
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MCT_FEEDBACK_DIR=/tmp/mct-feedback \
    HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user mct_service ./mct_service
COPY --chown=user dynamic_mct.py serve.py ./
COPY --chown=user static ./static
USER user
EXPOSE 7860
CMD ["sh", "-c", "uvicorn serve:app --host 0.0.0.0 --port ${PORT:-7860}"]
