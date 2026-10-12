"""Compare immutable pre-race records with separately supplied official outcomes."""
def render(key):
    import json
    import streamlit as st
    from .independent_ai_registry import settle
    with st.expander('レース後の答え合わせ'):
        st.caption('発走前固定JSONと、出典付きの確定結果JSONを選択してください。保存済み予測文は書き換えません。実4角がない場合は位置仮説を検証不能とします。')
        fixed=st.file_uploader('発走前固定JSON',type=['json'],key=key+'_review_fixed')
        outcome=st.file_uploader('確定結果JSON',type=['json'],key=key+'_review_outcome')
        if fixed is not None and outcome is not None and st.button('保存予測と結果を比較',key=key+'_review_run'):
            st.session_state.pop(key+'_review_result',None)
            try:
                record=json.loads(fixed.getvalue());actual=json.loads(outcome.getvalue())
                value=settle(record,actual)
                st.session_state[key+'_review_result']=value
            except (ValueError,KeyError,TypeError) as exc:st.warning('照合できません：'+str(exc))

        if key+'_review_result' in st.session_state:
            value=st.session_state[key+'_review_result']
            saved=value['commentary_review']['saved_commentary'] or {}
            for paragraph in saved.get('paragraphs',[]):st.write(paragraph)
            for row in value['commentary_review']['observations']:
                st.write(f"{row['horse_no']}番：{row['finding']} / 想定4角{row['expected']}・実4角{row['actual']} / 着順{row['finish']}")
            st.caption(value['commentary_review']['unverified'])
            st.write(f"仮想投資 {value['stake']}円 / 払戻 {value['payout']}円 / 損益 {value['profit']}円")
            st.download_button('答え合わせを別ファイルで保存',json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8'),file_name=f"independent_review_{value['race_id']}.json",key=key+'_review_download')
