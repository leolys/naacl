from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deps import core
import prompts
import prompts_v2


def test_prompt_only_type_fix_preserves_actor_and_all_other_words():
    assert prompts_v2.ACTOR==prompts.ACTOR
    for stage in ('GENERATE','QUESTIONS','SUPPLEMENT','VERIFY'):
        before=getattr(prompts,stage)
        after=getattr(prompts_v2,stage)
        assert after.replace(prompts_v2.NEW,prompts_v2.OLD)==before


@pytest.mark.parametrize('value', [True, False, 3, 2.5, 'Europe', None])
def test_exact_public_scalar_passes_without_adaptation(value):
    core._evidence({'ref':'public_task','path':'/value','content':value},{'value':value})


@pytest.mark.parametrize('leaf,content', [(True,'true'),(False,'false'),(True,1),(1,True),
                                           (3,'3'),(None,'null'),('Europe','europe')])
def test_wrong_type_or_value_is_not_repaired(leaf,content):
    with pytest.raises(core.SchemaError):
        core._evidence({'ref':'public_task','path':'/value','content':content},{'value':leaf})


@pytest.mark.parametrize('citation', [
    {'ref':'public_task','path':'/missing','content':True},
    {'ref':'public_task','path':'/value'},
    {'ref':'public_task','path':'/value','content':[]},
    {'ref':'public_task','path':'/value','content':{}}])
def test_no_path_lookup_or_missing_content_repair(citation):
    with pytest.raises(core.SchemaError):
        core._evidence(citation,{'value':True})
