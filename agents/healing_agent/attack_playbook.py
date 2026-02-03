# Handles decisions from the DecisionAgent and triggers alerts for self-healing if label indicates attack
# This is a new playbook for handling attack labels from decisions

def handle_attack_decision(self, decision):
    label = None
    if hasattr(decision, 'metadata') and decision.metadata:
        label = decision.metadata.get('label', None)
    if label and str(label).lower() not in ["benign", "normal", ""]:
        # Trigger an alert for self-healing
        alert = Alert(
            alert_id=f"ALERT-{int(time.time())}",
            alert_type=IncidentType.PERF_DROP,  # Or a new type if needed
            severity="CRITICAL",
            timestamp=datetime.utcnow().isoformat(),
            metrics_snapshot={},
            description=f"Attack detected by DecisionAgent: label={label}"
        )
        self.producer.send('alerts', alert.to_json())
        logger.info(f"Triggered self-healing alert for attack label: {label}")
