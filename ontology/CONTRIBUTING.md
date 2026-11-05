# Contributing: the PR process

`main` is protected. Nobody (admins included) pushes to it directly.

1. Branch from `main` (`git switch -c feat/short-name`).
2. Make the change. Run the checks locally (see README, "Run the checks").
3. Open a pull request using the template.
4. The **`tests`** GitHub Actions workflow runs: Turtle parsing, OWL 2 DL profile,
   HermiT reasoning (fails on inconsistency or unsatisfiable classes), ROBOT report,
   SHACL completeness, SPARQL competency queries, and the worked-example numbers.
5. A reviewer (human or the Grok Bot reviewer agent) reads the diff. **Only after the
   diff is reviewed AND `tests` is green**, the reviewer posts the commit status
   `Grok Bot QC` = `success` on the PR head commit:

   ```bash
   gh api repos/supergus/pla-agents/statuses/<head-sha> \
     -f state=success -f context="Grok Bot QC" -f description="Diff reviewed; tests passed"
   ```

6. Merge (the branch-protection rule requires the `Grok Bot QC` status; 0 approvals).

Branch protection on `main`: PR required, required status `Grok Bot QC`,
0 required approvals, enforced for admins, no force pushes, no deletions.

## Modelling conventions

- Turtle only, one module per concern, 4-space indents, terms grouped Classes / Object
  properties / Datatype properties / Individuals.
- Every term: `rdfs:label` (unique, lower case) and `rdfs:comment` (one or two sentences).
- Classes in `UpperCamelCase`, properties in `lowerCamelCase`, all in
  `https://supergus.github.io/rfq-ontology/ns#`.
- Use `owl:FunctionalProperty`, inverses, transitivity and disjointness only where they
  are true of the business, and say why in the comment.
- Arithmetic belongs in `scripts/`, not in OWL.
- Stay inside OWL 2 DL (CI checks the profile). Use `xsd:dateTime`, not `xsd:date`.
