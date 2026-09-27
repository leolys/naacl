"""Archive received review documents and exact request messages; no reviewer calls."""
from datetime import datetime, timezone
import shutil
from deps import HERE, PROJECT, wire

CLAIM_REQUEST = '''RESULT-TO-CLAIM EVALUATION, fresh same-family provisional review. Workdir D:/ths_Viswork. Read research/online_defense_20260925/idea-stage/docs/research_contract.md, PROTOCOL.md, METHOD_REVISED_ZH.md, RESULT_SUMMARY.json, EVIDENCE.json (read relevant fields instead of dumping it), evidence_precheck.json, and original live_v1/*/result.json and step_*/defense/verified.json as needed. Intended engineering claim: an explanation-set completion/check/rule-persistence pipeline runs inside one original web task before first primary action executes, then normal actor performs real POST. No assumed success or forced conflict generation. Fixed panel b001,b002,pub013 x original/clean x ordinary/method =12. Observed ordinary true submitted+original score success 5/6; method 1/6. Method 6 hooks,5 completed verification,1 prompt/schema mismatch,2 actor cap with invalid explicitly cited dependencies,2 unresolved. All280 original route/POST offline controls pass, not model outcomes. Shared current budget160 attempts/600 browserops/$10 estimated,noGPU. One interface-only debug will separately fix Boolean scalar prompt wording; NOT replace v1 and no extra research runs. Judge (1) narrow engineering lifecycle support, (2) full-scale research readiness, (3) lack of evidence for benefit/persistence/semantic coverage. Inspect whether claims confuse O/B with action, refusal with success, or reviewer conclusions with human audit. Need genuine residual issues without proposing task-specific answer rules, forced submission, or another large framework. Dataset original charts/gold kept, including their visible captions. No model calls or file edits outside your review outputs. Output structured claim_supported yes|partial|no; what_results_support/dont_support; missing_evidence; suggested_claim_revision; next_experiments_needed (recommendations ONLY); confidence. Save full response research/online_defense_20260925/reviews/CLAIMS_FROM_RESULTS.md and parsed judgment .json. User scope overrides automatic skill routing: do not launch any follow-up experiment, extend full140, alter prompts, or change data. This review is same-family/provisional, not independent human validation.'''
CLAIM_FOLLOWUP = '''Final bounded interface debug now complete: live_v2_schema_debug b002 official method one pass,10 new requests,3 browserops, verification completed, actual rule_state_v1 +v2 via one actor challenge/reverification, ultimately unresolved_public_evidence and no primary select/POST. v1 unchanged. EVIDENCE.json/RESULT_SUMMARY.json freshly regenerated (104 attempts99browserops estimated$3.136828 total). REPORT.md and ONLINE_DEFENSE_REVIEW.html created. Please incorporate this separately in your final review, not as13th efficacy sample and do not merge/replace6methodcells. All real inference stopped.'''
HTML_REQUEST = '''You are an independent ARIS HTML render auditor. Fresh thread, same-family provisional. Read directly D:/ths_Viswork/research/online_defense_20260925/REPORT.md, EVIDENCE.json, READER_NOTES_ZH.json and generated ONLINE_DEFENSE_REVIEW.html. Generator build_review.py reuses project .agents/skills/render-html/scripts/render_html.py academic template and adds escaped records + code-embedded verified local PNG/JPEG data URIs. Those trusted data bitmaps/CSS are expected; raw untrusted model HTML is not. Task audit faithful, safe, structurally usable rendering ONLY, not claim truthfulness. Checks: all report sections/tables/code/list content present;13 actual unit sections including12fixed+1separatedebug; initialsets/questions/supplement/verification/rule states/actor timelines/full system+user input text and image references not silently dropped; input screenshot is pre-action not post-action; source hashes match; safe escaping, no unexpected scripts/handlers/external requests/template leaks. Output STRICT JSON first then short prose with verdict PASS|WARN|FAIL|ERROR, review_independence same-family, acceptance_status provisional, checks{source_hash_match,information_fidelity,structure,math_code_tables,callouts,safety_escaping,placeholder_leak}, blocking_issues[],warnings[],summary. Expected metadata/header/TOC/sanitization differences are allowed. Save full raw review reviews/HTML_REVIEW.md and parsed sidecar ONLINE_DEFENSE_REVIEW.html.review.json. No API calls, no source/HTML changes, do not judge method benefit. PASS only if no material fidelity/safety issue; WARN cosmetic only; FAIL for missing/alteredmeaningful content,bad hash,unsafe content. Root handles local browser visual QA separately.'''


def archive(skill, number, purpose, messages, response, agent, effort):
    folder=PROJECT/'.aris/traces'/skill/'2026-09-26_online_defense'
    folder.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc).isoformat()
    runmeta=folder/'run.meta.json'
    if not runmeta.exists():
        wire.dump(runmeta,{'skill':skill,'run_id':'2026-09-26_online_defense','recorded_at':now,
            'executor':'codex','executor_model':'not_logged','executor_family':'openai',
            'review_independence':'same-family','acceptance_status':'provisional','project_dir':str(PROJECT)})
    prefix='%03d-%s'%(number,purpose)
    request={'call_number':number,'purpose':purpose,'timestamp':now,'timestamp_kind':'trace_archival_time',
        'tool':'spawn_agent/followup_task with actual message records','model':'gpt-5.6-sol',
        'reasoning_effort':effort,'prompt':'\n\n'.join(m['message'] for m in messages),'messages':messages,
        'files_referenced':[str(response.relative_to(PROJECT))]}
    wire.dump(folder/(prefix+'.request.json'),request)
    shutil.copy2(response,folder/(prefix+'.response.md'))
    wire.dump(folder/(prefix+'.meta.json'),{'call_number':number,'purpose':purpose,'timestamp':now,
        'agent_id':agent,'model':'gpt-5.6-sol','reviewer_family':'openai','review_independence':'same-family',
        'acceptance_status':'provisional','duration_ms':None,'status':'ok',
        'response_source':'Full saved reviewer report; any executor framing in source document is retained and identified.',
        'response_file_sha256':wire.digest(response)})
    return {'event':'review_trace','skill':skill,'purpose':purpose,'agent_id':agent,
        'trace_path':str(folder.relative_to(PROJECT)).replace('\\','/'),
        'review_independence':'same-family','acceptance_status':'provisional','status':'ok'}


def main():
    messages=wire.read(HERE/'reviews/REVIEW_REQUESTS_RAW.json')
    groups=[('predeployment',['initial_code_review','fix_follow_up'],'CODE_REVIEW.md'),
        ('first-live-dependencies',['first_live_or_and_diagnosis'],'FIRST_LIVE_DIAGNOSTIC.md'),
        ('scalar-schema',['scalar_review'],'SCHEMA_REVIEW.md'),
        ('v2-batch',['current_v2_batch_gate','current_v2_batch_provenance_follow_up'],'V2_AND_BATCH_REVIEW.md'),
        ('batch-fix',['batch_safety_fix_review'],'BATCH_FIX_REVIEW.md')]
    events=[]
    for index,(purpose,stages,filename) in enumerate(groups,1):
        events.append(archive('experiment-bridge',index,purpose,[m for m in messages if m['stage'] in stages],
                              HERE/'reviews'/filename,'/root/online_code_review','xhigh'))
    events.append(archive('result-to-claim',1,'bounded-lifecycle',
        [{'message':CLAIM_REQUEST},{'message':CLAIM_FOLLOWUP}],HERE/'reviews/CLAIMS_FROM_RESULTS.md',
        '/root/online_result_claim_review','ultra'))
    events.append(archive('render-html',1,'standalone-evidence-view',[{'message':HTML_REQUEST}],
        HERE/'reviews/HTML_REVIEW.md','/root/online_html_audit','xhigh'))
    # Event records are returned for append-only registration by the executor.
    wire.dump(HERE/'review_trace_events.json',events)
    print('Archived',len(events),'review reports with exact available request messages.')


if __name__=='__main__':main()
