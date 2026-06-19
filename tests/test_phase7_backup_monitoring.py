from __future__ import annotations

import os
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).parent.parent

# Test the backup script logic (without actually running pg_dump)
class TestBackupScript:
    def test_backup_script_exists(self) -> None:
        backup_script = WORKSPACE_ROOT / "scripts" / "backup.sh"
        assert backup_script.exists()
        assert backup_script.is_file()
        # Check executable permission
        assert os.access(backup_script, os.X_OK)

    def test_restore_script_exists(self) -> None:
        restore_script = WORKSPACE_ROOT / "scripts" / "restore.sh"
        assert restore_script.exists()
        assert restore_script.is_file()
        # Check executable permission
        assert os.access(restore_script, os.X_OK)

    def test_backup_script_help_pattern(self) -> None:
        # Check that script contains usage pattern
        content = (WORKSPACE_ROOT / "scripts" / "backup.sh").read_text()
        assert "Usage:" in content
        assert "full|schema|custom" in content

    def test_restore_script_help_pattern(self) -> None:
        # Check that script contains usage pattern
        content = (WORKSPACE_ROOT / "scripts" / "restore.sh").read_text()
        assert "Usage:" in content
        assert "<backup_file>" in content

    def test_monitoring_docker_compose_exists(self) -> None:
        compose_file = WORKSPACE_ROOT / "docker-compose.monitoring.yml"
        assert compose_file.exists()
        assert compose_file.is_file()

    def test_prometheus_config_exists(self) -> None:
        config_file = WORKSPACE_ROOT / "monitoring" / "prometheus" / "prometheus.yml"
        assert config_file.exists()
        assert config_file.is_file()
        
        content = config_file.read_text()
        assert "scrape_interval:" in content
        assert "chatbot_api" in content
        assert "alert_rules.yml" in content

    def test_alert_rules_exist(self) -> None:
        rules_file = WORKSPACE_ROOT / "monitoring" / "prometheus" / "alert_rules.yml"
        assert rules_file.exists()
        assert rules_file.is_file()
        
        content = rules_file.read_text()
        assert "ChatbotAPIDown" in content
        assert "ChatbotBackupMissing" in content
        assert "ChatbotDatabaseDown" in content

    def test_grafana_dashboard_exists(self) -> None:
        dashboard_file = WORKSPACE_ROOT / "monitoring" / "grafana" / "dashboards" / "system-overview.json"
        assert dashboard_file.exists()
        assert dashboard_file.is_file()
        
        content = dashboard_file.read_text()
        assert '"title": "Chatbot Core - System Overview"' in content
        assert "API Status" in content
        assert "Database Status" in content

    def test_backup_retention_logic(self) -> None:
        # Test that backup script mentions retention
        content = (WORKSPACE_ROOT / "scripts" / "backup.sh").read_text()
        assert "RETENTION_DAYS" in content
        assert "mtime +" in content  # find command for old files

    def test_restore_safety_check(self) -> None:
        # Test that restore script has safety confirmation
        content = (WORKSPACE_ROOT / "scripts" / "restore.sh").read_text()
        assert "FORCE=" in content
        assert "Type 'RESTORE' to confirm" in content
        assert "pg_terminate_backend" in content  # connection termination
