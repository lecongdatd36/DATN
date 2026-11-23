"""Use a new disposable SQL Server database for each regression run."""
import os
from pathlib import Path
import runpy

os.environ["DJANGO_SETTINGS_MODULE"] = "QLNH.sqlserver_test_settings"
runpy.run_path(str(Path(__file__).with_name("run_tests.py")), run_name="__main__")
