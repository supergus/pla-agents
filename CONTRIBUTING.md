# Contributing: the PR process

`main` is protected. Nobody (admins included) pushes to it directly.

1. Branch from `main` (`git switch -c feat/short-name`).
2. Make the change. Run `python scripts/fetch_ontology.py && python -m pytest` locally.
3. Open a pull request using the template.
4. The **`tests`** GitHub Actions workflow runs: fetches the ontology at the commit in `ontology.lock`, then runs
   pytest (contracts vs ontology, worked-example numbers, end-to-end RFQ-1002, retries, crash/resume, agentic gates).
   No test calls a live model.
5. A reviewer (human or the Grok Bot reviewer agent) reads the diff. **Only after the diff is reviewed AND `tests`
   is green**, the reviewer posts the commit status `Grok Bot QC` = `success` on the PR head commit:

   ```bash
   gh api repos/supergus/rfq-agents/statuses/<head-sha> \
     -f state=success -f context="Grok Bot QC" -f description="Diff reviewed; tests passed"
   ```

6. Merge (the branch-protection rule requires the `Grok Bot QC` status; 0 approvals).

Branch protection on `main`: PR required, required status `Grok Bot QC`, 0 required approvals, enforced for
admins, no force pushes, no deletions.

## Conventions

- Python 3.12+, dependencies limited to rdflib, pyshacl, pytest. No agent framework.
- A new tool needs: a contract in `rfq_agents/contracts/tools.ttl` **and** a matching `rfq:Tool` individual in
  rfq-ontology (land that first, then bump `ontology.lock`), an implementation registered with `@tool`, and tests.
- Agentic tools must validate model output (schema, then SHACL) before returning triples, and turn low confidence
  into Issues. Never compute prices in an LLM.
- No secrets in the repo. Credentials come from the environment only.
- Upgrading the ontology = a PR that changes only `ontology.lock` (plus any fixes it forces).
