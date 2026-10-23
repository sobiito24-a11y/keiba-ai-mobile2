"""Check real client sort/filter rules without reranking prediction records."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


NODE=shutil.which("node")
JS=Path(__file__).parents[1]/"core/game_ui_assets/race_comparison.js"
pytestmark=pytest.mark.skipif(NODE is None,reason="Node.js is required for client rule checks")


def node_check(code):
    script="const assert=require('node:assert/strict');const rules=require("+json.dumps(str(JS))+");\n"+code
    result=subprocess.run([NODE,"-e",script],capture_output=True,text=True,check=False)
    assert result.returncode==0,result.stderr or result.stdout


@pytest.mark.parametrize("kind",["number","rank"])
def test_numeric_sort_preserves_zero_negatives_and_missing_last_both_directions(kind):
    node_check("""
const source=[10,null,-2,2,0,undefined,NaN,Infinity,'3'];
const before=source.slice();
const asc=source.slice().sort((a,b)=>rules.compareValues(a,b,TYPE,'asc'));
const desc=source.slice().sort((a,b)=>rules.compareValues(a,b,TYPE,'desc'));
// Undefined is sorted to the end by Array.sort itself; it still is missing.
assert.deepEqual(asc.slice(0,5),[-2,0,2,10,null]);
assert.deepEqual(desc.slice(0,5),[10,2,0,-2,null]);
for(const value of [null,undefined,NaN,Infinity,'3']){
 assert.equal(rules.compareValues(value,2,TYPE,'asc'),1);
 assert.equal(rules.compareValues(value,2,TYPE,'desc'),1);
}
assert.deepEqual(source,before);
""".replace("TYPE",json.dumps(kind)))


@pytest.mark.parametrize("kind,values,asc",[
    ("text",["馬10","馬2","馬1"],["馬1","馬2","馬10"]),
    ("grade",["D","B","A","C"],["A","B","C","D"]),
    ("boolean",[True,False],[False,True]),
])
def test_text_grade_and_user_checks_use_their_own_sort_types(kind,values,asc):
    node_check("""
const source=VALUES;
const sorted=source.slice().sort((a,b)=>rules.compareValues(a,b,TYPE,'asc'));
assert.deepEqual(sorted,EXPECTED);
assert.deepEqual(source,VALUES);
for(const direction of ['asc','desc']){
 assert.equal(rules.compareValues(null,source[0],TYPE,direction),1);
 assert.equal(rules.compareValues(source[0],null,TYPE,direction),-1);
}
""".replace("VALUES",json.dumps(values,ensure_ascii=False)).replace("TYPE",json.dumps(kind)).replace("EXPECTED",json.dumps(asc,ensure_ascii=False)))


def test_compound_filters_apply_and_keep_exact_prediction_values_immutable():
    node_check("""
const specs={odds:{key:'odds',type:'number'},rest:{key:'rest',type:'number'},
 training:{key:'training',type:'grade'},jockey:{key:'jockey',type:'text'},
 user:{key:'user',type:'boolean'}};
const horses=[
 {no:1,odds:2.1,rest:21,training:'A',jockey:'武豊',user:true,score:91.123456789},
 {no:2,odds:8.6,rest:70,training:'B',jockey:'横山武史',user:true,score:92.2},
 {no:3,odds:null,rest:180,training:'A',jockey:'武豊',user:false,score:99.3}];
const before=JSON.stringify(horses);
const filters={odds:rules.cleanFilter({min:'1',max:'4'},specs.odds),
 rest:rules.cleanFilter({min:'7',max:'30'},specs.rest),
 training:rules.cleanFilter({choice:'A'},specs.training),
 jockey:rules.cleanFilter({text:'武'},specs.jockey),
 user:rules.cleanFilter({choice:'selected'},specs.user)};
assert.deepEqual(horses.filter(h=>Object.entries(filters).every(([key,f])=>rules.matchesFilter(h[key],f,specs[key]))).map(h=>h.no),[1]);
assert.equal(JSON.stringify(horses),before);
assert.equal(horses[0].score,91.123456789);
assert.equal(rules.matchesFilter(null,{presence:'missing'},specs.odds),true);
assert.equal(rules.matchesFilter(0,{presence:'missing'},specs.odds),false);
assert.equal(rules.matchesFilter(null,{presence:'known'},specs.odds),false);
assert.equal(rules.matchesFilter(false,{choice:'unselected'},specs.user),true);
assert.equal(rules.matchesFilter(false,{choice:'selected'},specs.user),false);
""")


def test_past_index_numeric_range_and_condition_text_can_be_combined():
    node_check("""
const spec={key:'run_old',type:'number',text_key:'run_old_condition'};
const filter=rules.cleanFilter({min:'8',max:'15',text:'門別'},spec);
assert.equal(rules.matchesFilter(12,filter,spec,'門別・ダ1000m・右'),true);
assert.equal(rules.matchesFilter(16,filter,spec,'門別・ダ1000m・右'),false);
assert.equal(rules.matchesFilter(12,filter,spec,'東京・芝1600m・左'),false);
assert.equal(rules.matchesFilter(null,filter,spec,'門別・ダ1000m・右'),false);
const name={key:'name',type:'text'};
assert.equal(rules.matchesFilter('テストＡ',{text:'テストa'},name),true);
""")


def test_invalid_or_empty_filters_cannot_silently_change_valid_conditions():
    node_check("""
const spec={key:'odds',type:'number'};
const original={min:1,max:5};
assert.throws(()=>rules.cleanFilter({min:6,max:5},spec),RangeError);
assert.throws(()=>rules.cleanFilter({min:'Infinity'},spec),RangeError);
assert.deepEqual(original,{min:1,max:5});
assert.equal(rules.cleanFilter({presence:'all',min:'',max:''},spec),null);
assert.deepEqual(rules.cleanFilter({presence:'missing',min:1,max:5},spec),{presence:'missing'});
assert.deepEqual(rules.cleanFilter({presence:'missing',min:100,max:1},spec),{presence:'missing'});
assert.deepEqual(rules.cleanFilter({presence:'missing',min:'Infinity'},spec),{presence:'missing'});
assert.equal(rules.cleanFilter({choice:'X'},{key:'training',type:'grade'}),null);
assert.equal(rules.cleanFilter({choice:'AI'},{key:'user',type:'boolean'}),null);
""")
