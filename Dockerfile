# Defaults to match Architectures in template.yaml — without it a build on an
# arm64 machine produces an image Lambda refuses to run. Override with
# --build-arg LAMBDA_PLATFORM=linux/arm64 if the template switches to arm64.
ARG LAMBDA_PLATFORM=linux/amd64
FROM --platform=${LAMBDA_PLATFORM} public.ecr.aws/lambda/python:3.12

COPY requirements.txt ./
# pip's default 15s socket timeout gives up on a slow link and then reports the
# package as having "no versions" rather than as a network failure. Raising the
# timeout and retry count keeps the build honest on constrained connections.
RUN pip install --no-cache-dir --disable-pip-version-check \
    --timeout 120 --retries 10 \
    -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY src/ ${LAMBDA_TASK_ROOT}/src/

CMD ["src.main.handler"]
