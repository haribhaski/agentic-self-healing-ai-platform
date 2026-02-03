import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
import mlflow
import mlflow.sklearn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MLOpsTraining")

def generate_synthetic_data(n_samples=10000):
    """Generate synthetic credit risk data"""
    np.random.seed(42)
    
    credit_scores = np.random.normal(700, 80, n_samples).clip(300, 850)
    debt_ratios = np.random.beta(2, 5, n_samples) * 100
    income = np.random.lognormal(10.5, 0.7, n_samples)
    loan_amounts = np.random.lognormal(10, 0.8, n_samples)
    employment_years = np.random.exponential(5, n_samples).clip(0, 40)
    
    risk_score = (
        -0.005 * credit_scores +
        0.02 * debt_ratios +
        -0.00001 * income +
        0.00003 * loan_amounts +
        -0.02 * employment_years +
        np.random.normal(0, 0.5, n_samples)
    )
    
    labels = (risk_score > np.percentile(risk_score, 60)).astype(int)
    
    data = pd.DataFrame({
        'credit_score': credit_scores,
        'debt_ratio': debt_ratios,
        'income': income,
        'loan_amount': loan_amounts,
        'employment_years': employment_years,
        'label': labels
    })
    
    return data

def train_model(experiment_name="credit_risk_model"):
    """Train and log model to MLflow"""
    mlflow.set_tracking_uri("http://localhost:5020")
    mlflow.set_experiment(experiment_name)
    
    logger.info("Generating synthetic training data...")
    data = generate_synthetic_data(10000)
    
    X = data[['credit_score', 'debt_ratio', 'income', 'loan_amount', 'employment_years']]
    y = data['label']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    with mlflow.start_run():
        logger.info("Training Random Forest model...")
        
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred)
        recall = recall_score(y_test, y_pred)
        
        logger.info(f"Model Performance:")
        logger.info(f"  Accuracy: {accuracy:.4f}")
        logger.info(f"  F1 Score: {f1:.4f}")
        logger.info(f"  Precision: {precision:.4f}")
        logger.info(f"  Recall: {recall:.4f}")
        
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("max_depth", 10)
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall", recall)
        
        mlflow.sklearn.log_model(
            model,
            "model",
            registered_model_name="credit_risk_model"
        )
        
        logger.info("Model trained and logged to MLflow successfully!")
        logger.info(f"Run ID: {mlflow.active_run().info.run_id}")

if __name__ == "__main__":
    train_model()
