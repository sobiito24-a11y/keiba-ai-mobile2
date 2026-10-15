"""Download-backed paper records; no automatic purchase or prediction writes."""
import json
from . import paper_betting as p
from . import race_odds as o

def current_decision(result,view):
 import streamlit as st
 identity=o.identity_from_result(result);initial=o.state_for(result)
 key='race_prices_'+o.digest(dict(identity=identity,saved=initial))
 state=st.session_state.get(key,initial)
 # Exact displayed observation only; never combine clocks or ticket markets.
 quotes=state['saved']+state['history'];quote=None
 index=st.session_state.get(key+'_observation_'+str(len(quotes)),len(quotes)-1)
 if quotes and isinstance(index,int) and 0<=index<len(quotes):quote=quotes[index]
 decision=p.build(view,result.race_mode,identity,quote)
 return decision

def render(result,view):
 import streamlit as st
 decision=current_decision(result,view)
 rid=str(decision['race_id']);bucket='paper_record_'+rid
 with st.expander('馬券判断の記録・結果照合',expanded=False):
  st.caption('セッションは永続保存ではありません。固定JSONをダウンロードしてください。価格取得時刻不明は発走前価格と保証できません。')
  action=st.radio('今回の記録',['買い目未記録','購入なし・見送り','自分の買い目を記録'],key=bucket+'_action')
  ticket_key=bucket+'_user_tickets'
  tickets=st.session_state.setdefault(ticket_key,[])
  if action=='自分の買い目を記録':
   with st.form(bucket+'_ticket_form'):
    kind=st.selectbox('券種',list(p.KINDS),format_func=lambda k:p.LABELS[k])
    numbers=st.multiselect('馬番（単勝・複勝は1頭、ワイド・馬連は2頭）',[int(n) for n in decision['runner_numbers']])
    stake=st.number_input('金額（円）',min_value=100,step=100,value=100)
    add=st.form_submit_button('買い目を追加')
   if add:
    try:
     trial=tickets+[dict(kind=kind,horses=numbers,stake=int(stake))]
     p.freeze_user(decision,trial,'tickets')
     st.session_state[ticket_key]=trial;tickets=trial
    except (ValueError,TypeError) as exc:st.error(str(exc))
   if tickets:st.dataframe([dict(券種=p.LABELS[t['kind']],馬番='－'.join(map(str,t['horses'])),金額=t['stake']) for t in tickets],hide_index=True)
   if st.button('入力した買い目をクリア',key=bucket+'_clear'):st.session_state[ticket_key]=[];st.rerun()
  before=st.checkbox('結果をまだ確認しておらず、対象レースの発走前であることを確認した',key=bucket+'_before')
  if st.button('現在の判断を固定する',key=bucket+'_freeze',disabled=not before):
   if bucket not in st.session_state:
    try:st.session_state[bucket]=p.freeze_user(decision,tickets if action=='自分の買い目を記録' else [],{'買い目未記録':'unrecorded','購入なし・見送り':'skip','自分の買い目を記録':'tickets'}[action],before)
    except (ValueError,TypeError) as exc:st.error(str(exc))
   else:st.info('このセッションでは既存の固定記録を保持しています。')
  record=st.session_state.get(bucket)
  if record:
   st.code(record['record_hash'])
   st.download_button('固定した馬券判断JSONを保存',json.dumps(record,ensure_ascii=False,indent=2),file_name=rid+'_paper_decision.json',key=bucket+'_download')
  st.caption('後日、固定判断JSONと公式結果の照合JSONを読み込みます。結果JSONはrace_id、source、tickets（kind／horses／status: hit・miss・refund／payout_per_100）を指定。未取得はunknownのまま残します。')
  saved=st.file_uploader('固定判断JSON',type=['json'],key=bucket+'_record')
  results=st.file_uploader('結果・払戻照合JSON',type=['json'],key=bucket+'_results')
  if saved and results:
   try:
    original=json.loads(saved.getvalue());out=p.settle(original,json.loads(results.getvalue()))
    st.json(out)
    st.download_button('精算結果JSONを保存',json.dumps(out,ensure_ascii=False,indent=2),file_name=str(out['race_id'])+'_settlement.json',key=bucket+'_settled')
   except (ValueError,TypeError,KeyError) as exc:st.error(str(exc))
 return decision
