from rfq_agents.__main__ import main


def test_cli_end_to_end(db, capsys):
    a = ["--db", str(db)]
    assert main(["run", "--rfq", "data/rfq-1002-incomplete.ttl", "--run-id", "1002-cli", "--quote-date", "2026-10-27",
                 "--base-delay", "0", "--inject-failure", "match_library_part:1"] + a) == 0
    assert "missing Incoterm" in capsys.readouterr().out
    assert main(["run", "--resume", "1002-cli", "--fix", "data/fixes/rfq-1002-fix.ttl", "--base-delay", "0",
                 "--inject-failure", "match_library_part:1"] + a) == 0
    out = capsys.readouterr().out
    assert "waiting_approval" in out and "retryOf=" in out and "$58.32" in out
    assert main(["run", "--resume", "1002-cli", "--approve", "--by", "chris"] + a) == 0
    assert "status=done" in capsys.readouterr().out
    assert main(["run", "--resume", "1002-cli", "--approve"] + a) == 1  # no pending gate any more
    assert main(["status", "1002-cli"] + a) == 0


def test_cli_crash_then_resume(db, capsys):
    a = ["--db", str(db)]
    assert main(["run", "--rfq", "data/rfq-1001.ttl", "--run-id", "c1", "--quote-date", "2026-10-27",
                 "--inject-failure", "cost_quote:crash"] + a) == 3
    assert main(["run", "--resume", "c1"] + a) == 0
    assert "$60.86" in capsys.readouterr().out
