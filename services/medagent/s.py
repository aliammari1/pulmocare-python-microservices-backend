import mlflow

model_path = "./Model/code/cxr_report_gen_mlflow_wrapper.py"

with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        python_model=model_path,  # Define the model as the path to the Python file
        artifact_path="./Model/artifacts",
    )

# Loading the model behaves exactly as if an instance of MyModel had been logged
my_model = mlflow.pyfunc.load_model(model_info.model_uri)
