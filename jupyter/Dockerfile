FROM quay.io/jupyter/pyspark-notebook:spark-3.5.3
USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.10 boto3==1.35.99
USER ${NB_UID}
CMD ["start-notebook.py", "--ServerApp.token=", "--ServerApp.password="]
