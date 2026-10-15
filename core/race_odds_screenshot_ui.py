"""Review-first image import; clipboard and file uploads share one OCR path."""
def render(identity, state, key):
    import hashlib
    import streamlit as st
    import pandas as pd
    from . import race_odds as odds
    from .race_odds_screenshot import draft, confirmed_quote, FIELDS, image_data, saved_name_candidate, adopt_saved_name, identity_binding
    from .race_odds_clipboard import render as paste_images
    st.caption('PC・スマホの単勝／複勝表に対応。小さい画像はブラウザーで拡大して撮り直すか、馬番・馬名・単勝・複勝を含む表部分を切り取ってください。列が不明な場合も確認表で修正できます。')
    scope='st-key-'+key+'_screenshot_panel'
    st.markdown('<style>.'+scope+' details>summary,.'+scope+' button{background:#172b43!important;color:#eef5ff!important}.'+scope+' details>summary p,.'+scope+' button p{color:#eef5ff!important}</style>',unsafe_allow_html=True)
    with st.container(key=key+'_screenshot_panel'), st.expander('スクショから単複オッズを取込', expanded=False):
        st.write('画像と全頭の馬番・馬名・単複数値を確認し、修正後に一括反映します。人気順位は馬番に使用しません。')
        try: pasted=paste_images(key+'_clipboard')
        except (ValueError,OSError) as exc:
            st.error(str(exc));pasted=[]
        uploads=st.file_uploader('単勝・複勝のスクリーンショット（貼り付けと合計最大5枚）',type=['png','jpg','jpeg','webp'],
                                 accept_multiple_files=True,key=key+'_images')
        files=pasted+[(u.name,u.getvalue()) for u in (uploads or [])]
        # A pasted image uploaded again is the same source, not a second reading.
        files=list({hashlib.sha256(raw).hexdigest():(name,raw) for name,raw in files}.values())
        signature=odds.digest([(name,hashlib.sha256(raw).hexdigest()) for name,raw in files])
        draft_key=key+'_ocr_'+signature
        if st.button('画像を読み取る',disabled=not files or len(files)>5,key=key+'_ocr_run'):
            try:
                with st.spinner('ローカルOCRで読取中…'):
                    value=draft(files,identity)
                st.session_state[draft_key]=value
                for suffix in ('_base','_work','_fingerprint','_confirmed'):
                    st.session_state.pop(draft_key+suffix,None)
                st.session_state[draft_key+'_revision']=st.session_state.get(draft_key+'_revision',0)+1
            except (ValueError,OSError) as exc: st.error(str(exc))
        if len(files)>5: st.warning('貼り付けとファイル選択を合わせて最大5枚にしてください。')
        value=st.session_state.get(draft_key)
        if value is None:return
        if value.get('identity_binding') and value['identity_binding']!=identity_binding(identity):
            st.warning('対象レースが変わりました。画像を再読取してください。')
            return
        for message in value['messages']:st.warning(message)
        st.caption(f"OCR処理時間：{value['seconds']:.2f}秒。全数値の原画像照合が必要です。画像内の時計は価格更新時刻に使いません。")
        with st.expander('画像と保存済み出走馬を確認'):
            for name,raw in files:st.image(raw,caption=name)
            st.dataframe([{'馬番':h['horse_no'],'保存馬名':h['name']} for h in identity['horses']],hide_index=True)
        columns=list(FIELDS)+['読取注意']
        initial=[{k:r.get(k,'') for k in columns} for r in value['rows']]
        base=st.session_state.setdefault(draft_key+'_base',initial)
        work=st.session_state.get(draft_key+'_work',base)
        urgent=[i for i,r in enumerate(work) if r.get('読取注意')!='原画像と全項目を確認']
        if urgent:st.warning(f'要確認 {len(urgent)}行。馬番・馬名の不一致、再読取の食い違い、数値形式を確認してください。')
        else:st.info('OCRが一致した行も、すべての価格を画像と照合してください。')
        order=urgent+[i for i in range(len(work)) if i not in urgent]
        if order:
            index=st.selectbox('1頭ずつ確認・修正（要確認を先に表示）',order,
                format_func=lambda i:f"{'要確認 · ' if i in urgent else ''}{i+1}行目：{work[i].get('馬番') or '—'} {work[i].get('馬名') or '未読取'}",key=draft_key+'_row')
            original=value['rows'][index] if index<len(value['rows']) else {}
            raw=next((raw for _,raw in files if hashlib.sha256(raw).hexdigest()==original.get('_image_sha')),None)
            if raw is not None and original.get('_crop'):
                st.image(image_data(raw).crop(original['_crop']),caption='元画像の該当行（価格時刻は不明）',use_container_width=True)
                with st.expander('セル別の再読取結果'):
                    for label,cell in original.get('_ocr_cells',{}).items():
                        st.write(label+"："+" ／ ".join(v or "未読取" for v in cell.get("readings",[cell.get("primary"),cell.get("alternative")])))
                        if cell.get('disagreement') and cell.get('box'):
                            st.image(image_data(raw).crop(cell['box']),caption=label)
            revision=st.session_state.get(draft_key+'_revision',0)
            candidate=saved_name_candidate(work[index],identity,value)
            if candidate is not None:
                st.write('OCR馬名：'+(str(work[index].get('馬名')) or '未読取'))
                st.write('保存済み正式馬名の候補：'+candidate)
                st.caption('対象レースID：'+str(identity['race_id'])+'。画像のレースIDを自動確認したものではありません。対象レースと原画像を照合してください。')
                if raw is not None and not original.get('_crop'):
                    st.image(raw,caption='馬番・馬名・単複価格を照合する元画像')
                token=odds.digest(work[index])[:12]
                accepted=st.checkbox('対象レース・馬番が一致し、元画像の馬名と単複価格を確認した',
                    key=draft_key+f'_adopt_check_{revision}_{index}_{token}')
                if st.button('確認して採用',key=draft_key+f'_adopt_{revision}_{index}_{token}',disabled=not accepted):
                    changed_row,event=adopt_saved_name(work[index],identity,value,accepted)
                    changed=[dict(r) for r in work];changed[index]=changed_row
                    value.setdefault('name_adoptions',[]).append(event)
                    st.session_state[draft_key+'_base']=changed
                    st.session_state[draft_key+'_work']=changed
                    st.session_state[draft_key+'_revision']=revision+1
                    st.session_state[draft_key+'_confirmed']=False
                    st.rerun()
            with st.form(draft_key+f'_row_form_{revision}_{index}'):
                inputs={}
                inputs['馬番']=st.text_input('馬番',str(work[index].get('馬番','')))
                inputs['馬名']=st.text_input('馬名',str(work[index].get('馬名','')))
                for field in FIELDS[2:]:inputs[field]=st.text_input(field,str(work[index].get(field,'')))
                saved=st.form_submit_button('この行の修正を保存')
            if saved:
                changed=[dict(r) for r in work];changed[index].update(inputs)
                st.session_state[draft_key+'_base']=changed
                st.session_state[draft_key+'_work']=changed
                st.session_state[draft_key+'_revision']=revision+1
                st.session_state[draft_key+'_confirmed']=False
                st.rerun()
        st.caption('全頭を一覧で確認できます。不明価格は空欄にし、重複行・別レース行は修正または削除してください。')
        revision=st.session_state.get(draft_key+'_revision',0)
        with st.expander('全頭の読取結果を確認・編集',expanded=False):
            edited=st.data_editor(pd.DataFrame(base,columns=columns).fillna(''),hide_index=True,num_rows='dynamic',
                                  use_container_width=True,key=draft_key+f'_editor_{revision}',disabled=['読取注意'])
        data=edited.fillna('').to_dict('records')
        fingerprint=odds.digest(data)
        if st.session_state.get(draft_key+'_fingerprint')!=fingerprint:
            st.session_state[draft_key+'_confirmed']=False
            st.session_state[draft_key+'_fingerprint']=fingerprint
        st.session_state[draft_key+'_work']=data
        confirmed=st.checkbox('画像と全頭の馬番・馬名・数値を確認した（欠損価格は未取得として反映）',key=draft_key+'_confirmed')
        if st.button('全頭一括反映',key=draft_key+'_apply',disabled=not confirmed):
            try:
                quote=confirmed_quote(data,identity,value,confirmed)
                merged=odds.merge(state['history'],[quote],identity)
                count=len(merged)-len(state['history']);state['history']=merged
                st.session_state[key+'_status']=(f"スクショ確認済み：{quote['horse_count']}／{quote['expected_horses']}頭の価格を取込。"
                    f"単勝未取得 {quote['coverage']['win']['expected']-quote['coverage']['win']['count']}頭、"
                    f"複勝未取得 {quote['coverage']['place']['expected']-quote['coverage']['place']['count']}頭。履歴追加 {count}件。")
                st.success(st.session_state[key+'_status'])
            except (ValueError,TypeError,KeyError) as exc: st.error(str(exc))
