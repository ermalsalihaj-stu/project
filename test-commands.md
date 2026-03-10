1. Përgatitje (një herë)
Nga rrënja e projektit (c:\Users\Berdyna Tech\Desktop\project):

cd "c:\Users\Berdyna Tech\Desktop\project"
pip install -r requirements.txt
Nëse përdor venv:

cd "c:\Users\Berdyna Tech\Desktop\project"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
2. Validimi i bundle-it
python main.py validate --bundle bundles/sample_01
Pritet: Validation OK. (ose me disa warnings).

3. Ekzekutimi i pipeline-it (test i plotë)
python main.py run --bundle bundles/sample_01
Pas përfundimit do të shfaqet diçka si: Run complete. Output: ...\runs\2026-03-09_HHMM_sample_01.

Me strict (dështon nëse daljet nuk përputhen me schema):

python main.py run --bundle bundles/sample_01 --strict
4. Testet automatike (pytest)
pytest tests\ -v
Ose test specifik:

pytest tests\test_pipeline_smoke.py -v
pytest tests\test_end_to_end_final_outputs.py -v
pytest tests\test_intake_context_agent.py -v
pytest tests\test_outputs_schema_valid.py -v
pytest tests\test_github_pr_poster.py -v
pytest tests\test_jira_ingest.py -v
5. Kontrolli i daljeve
Pas një run, hap dosjen e run-it (zëvendëso me emrin real të folderit):

dir runs
Pastaj shiko përmbajtjen, p.sh.:

type runs\2026-03-09_1234_sample_01\context_packet.json
type runs\2026-03-09_1234_sample_01\final_recommendation.json
type runs\2026-03-09_1234_sample_01\prd.md
6. Komanda opsionale
Post në GitHub PR (vetëm nëse ke GITHUB_TOKEN, GITHUB_REPO, GITHUB_PR_NUMBER në .env ose environment):

python main.py post-pr --run-dir runs\2026-03-09_1234_sample_01
Ingest nga Jira (vetëm nëse ke Jira të konfiguruar në .env):

set JIRA_JQL=project=MYPROJECT
python main.py ingest-jira --jql "project=MYPROJECT" --max-results 50
Renditje e shkurtër për testim të plotë
python main.py validate --bundle bundles/sample_01
python main.py run --bundle bundles/sample_01
pytest tests\ -v
Kontrollo runs\<run_dir>\ për prd.md, roadmap.json, experiment_plan.md, decision_log.md, backlog.csv dhe JSON-et e findings.
Këto komanda mjaftojnë për të testuar vetë tërë funksionalitetin e projektit.