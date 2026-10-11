"""Read-only explanation of saved marks. No ticket or purchase-navigation calls."""
from .race_insight_common import (facts, describe, label, leading_features, position_sentence,
                                  VERSION, GAP_CALIBRATION, narrative_horses)


def overview(horses, pace):
    leaders = [label(h) for h in horses if h['style'] == '逃']
    forward = [label(h) for h in horses if h['group'] == 'front']
    line = pace + 'ペース想定。' if pace in ('S', 'M', 'H') else '予測ペースは未取得。'
    if leaders:
        line += '過去脚質で逃げに分類されるのは' + '、'.join(leaders[:3]) + ('など。' if len(leaders) > 3 else '。')
    else:
        line += '過去脚質では逃げに分類された馬が確認できないが、今回逃げる馬がいないという意味ではない。'
    leading = sum(h['style'] == '先' for h in horses)
    unknown = sum(h['style'] not in ('逃', '先', '差', '追') for h in horses)
    line += f'過去脚質の先行は{leading}頭、今回の前方想定は{len(forward)}頭。'
    if unknown:
        line += f'脚質未取得が{unknown}頭あり、確認できた範囲の構成。'
    if forward:
        line += '前方で運ぶ想定は' + '、'.join(forward[:4]) + ('など。' if len(forward) > 4 else '。')
    line += {'H': '前で競り合えば消耗が進む流れ。後ろの馬も、脚質と能力の裏付けがあってこそ差す余地が生まれる。',
             'S': '前で脚を残せる形が考えられるが、位置だけで決まらず、後方勢の能力と仕掛けも焦点。',
             'M': '極端な前後の有利を置かず、道中のロスと仕掛けのタイミングを比べたい。'}.get(pace, '脚質だけからペースや差し有利を補わず、取得済みの位置情報までで考える。')
    return line


def overall(centers, opponents, extra, mode):
    if not centers:
        return ['保存された正式候補と印から中心を特定できない。欠損した評価を補わず、全体の比較は保留とする。']
    lead = centers[0]
    line = '中心の' + label(lead) + 'は'
    if mode == 'jra' and lead['formal_rank'] is not None:
        line += f"正式{int(lead['formal_rank'])}位。"
    elif lead['pure_rank'] is not None:
        line += f"純能力{int(lead['pure_rank'])}位。"
    else:
        line += '保存された印を起点に見る。'
    if lead['group'] == 'front':
        line += '前方で運ぶ中心として、追走で脚を使うか、余力を残せるかを見たい。'
        context = lead.get('narrative_context', {})
        if lead['pure'] is not None and context.get('front_max') == lead['pure']:
            line += '前方勢では純能力が最も高く、粘り込みを比較する際の基準になる。'
    elif lead['group'] in ('middle', 'back'):
        line += '前方勢を追う立場で、届く展開になるかだけでなく能力差も重要になる。'
    else:
        line += '今回位置が不明のため、展開を前提に信頼を上乗せできない。'
    if mode == 'jra':
        if lead['training'] in ('C', 'D'):
            line += '調教面の懸念もあり、展開だけで安心はできない。'
        elif lead['training'] in ('A', 'B') and lead['rest_days'] is not None:
            line += f"調教{lead['training']}は確認材料だが、前走から{lead['rest_days']:g}日の間隔も併せて見たい。"
    paragraphs = [line]
    # Highlight distinctive facts among ALREADY selected formal horses only.
    # This affects prose emphasis, not roles, ranks, marks, or selection order.
    peers = centers[1:] + [h for h in opponents if h['member']]
    prominent = next((h for h in sorted(peers, key=lambda h: -len(leading_features(h)))
                      if leading_features(h)), None)
    if prominent:
        features = leading_features(prominent)
        text = label(prominent) + ('は最終' + f"{int(prominent['formal_rank'])}位ながら、" if prominent['formal_rank'] is not None else 'は')
        text += '・'.join(features) + ('がいずれも1位。' if len(features) > 1 else 'が1位。')
        if prominent['pure'] is not None and lead['pure'] is not None:
            delta = prominent['pure'] - lead['pure']
            if delta > 0:
                text += '純能力では中心を' + f'{delta:.2f}' + '上回り、印の強さと能力面の強みは分けて見たい。'
        if prominent['group'] != lead['group'] and prominent['group'] in ('front', 'middle', 'back') and lead['group'] in ('front', 'middle', 'back'):
            position = {'front':'前方','middle':'中団','back':'後方'}[prominent['group']]
            text += position + 'から運ぶ比較対象で、'
            text += {'H':'Hペースで前が脚を使うかが中心との比較の分かれ目。',
                     'M':'Mペースでは中心に先に動かれた場合の対応も見たい。',
                     'S':'Sペースでは中心との位置の差を能力や仕掛けで補えるかが鍵。'}.get(prominent['pace'],'ペース不明のため位置の違いだけで優劣は決めない。')
        if mode == 'jra' and prominent['training'] in ('C', 'D'):
            text += '調教面も慎重な確認が必要。'
        if prominent['weight_change'] is not None and prominent['weight_change'] > 0:
            text += f"斤量も前走比+{prominent['weight_change']:g}kg。"
        paragraphs.append(text)
    alternatives = [h for h in opponents if h['member'] and h is not prominent and h['pace_effect'] == 'plus']
    if alternatives:
        h = alternatives[0]
        text = '一方、' + label(h)
        text += ('は前が残る形で持ち味を生かす相手。' if h['pace'] == 'S' else 'は前受け組が消耗する形で浮上する相手。')
        if h['pure'] is not None and lead['pure'] is not None and h['pure'] < lead['pure']:
            text += f"中心との純能力差は{lead['pure']-h['pure']:.2f}あり、展開の助けなしでも互角とは言い切れない。"
        if h['conditions']:
            text += h['conditions'][0] + 'の裏付けと、中心が余力を失うかを併せて見たい。'
        elif h['pure'] is None:
            text += '能力が未取得のため、展開だけで中心を逆転できるとは扱わない。'
        else:
            text += '条件指数上位の裏付けは確認できず、展開だけで優劣を決めない。'
        paragraphs.append(text)
    if extra:
        text = '追加の' + '・'.join(label(h) for h in extra) + 'は、本文に挙げた条件が揃う場合の注意対象。'
        if any(not h['close_gap'] for h in extra):
            text += '能力差の大きい馬も含むため、位置取り変化だけで上位と同等には扱わない。'
        paragraphs.append(text)
    if lead['pace'] == 'H':
        paragraphs.append('前の馬が競り合うか、力を温存できるかが分岐点。H想定だけで前を下げず、粘る能力と後方勢の能力・適性を比較したい。')
    elif lead['pace'] == 'S':
        paragraphs.append('前が脚を残す形を重く見るか、後方勢が能力で追い上げる形を重く見るかが比較の分かれ目になる。')
    elif lead['pace'] == 'M':
        paragraphs.append('一律の展開有利は置かず、前で運ぶ馬の残り目と後方勢の追い上げを比較したい。')
    else:
        paragraphs.append('ペース情報がないため、展開の後押しを前提に評価を決め切らない。')
    return paragraphs


def opponent_groups(opponents, paragraphs):
    """Partition existing prose by resolved formal membership, never rank or mark."""
    groups = []
    for member, title in [(True, '相手本線（正式Top5）'),
                          (False, 'その他の印付き馬（参考）')]:
        selected = [(h, paragraph) for h, paragraph in zip(opponents, paragraphs)
                    if h['member'] == member]
        if selected:
            groups.append(dict(title=title, horse_numbers=[h['no'] for h, _ in selected],
                               paragraphs=[paragraph for _, paragraph in selected]))
    return groups


def generate(result, rows, development):
    mode = result.race_mode
    horses = facts(result, rows, development)
    if mode == 'jra':
        from .jra_race_insight import select
    else:
        from .nar_race_insight import select
    centers, opponents, extra = select(horses)
    anchor = centers[0] if centers else None
    audit = {}
    for role, selected in [('center', centers), ('opponent', opponents), ('additional', extra)]:
        for h in selected:
            reasons = ['existing_final_mark'] if role != 'additional' else []
            if role == 'additional':
                if mode == 'nar':
                    from .nar_race_insight import additional_routes
                    reasons = additional_routes(h)
                else:
                    reasons = ['close_gap_condition_pace']
            audit[h['no']] = dict(role=role, route=reasons, positive=h['conditions'],
                                  risks=h['risks'], ability_gap=h['gap_to_group'])
    # Enrich only temporary prose objects AFTER candidate selection and audit.
    prose = narrative_horses(horses)
    centers, opponents, extra = ([prose[h['no']] for h in group] for group in (centers, opponents, extra))
    anchor = centers[0] if centers else None
    sections = [
        dict(title='展開予想', paragraphs=[overview(horses, development['pace_prediction'])]),
        dict(title='中心候補', paragraphs=[describe(h, mode, 'center', centers[1] if h is anchor and len(centers)>1 else anchor) for h in centers]
             or ['正式候補の印が未取得のため、中心候補は保留。']),
        dict(title='相手本線', paragraphs=[describe(h, mode, 'opponent', anchor) for h in opponents]
             or ['該当する印の馬は確認できません。']),
        dict(title='追加注目馬', paragraphs=[describe(h, mode, 'additional', anchor) for h in extra]
             or ['該当なし。']),
        dict(title='総合考察', paragraphs=overall(centers, opponents, extra, mode)),
    ]
    sections[2]['groups'] = opponent_groups(opponents, sections[2]['paragraphs'])
    insight = dict(version=VERSION, mode=mode, policy=mode+'_marked_explanation',
                gap_calibration=GAP_CALIBRATION, centers=[h['no'] for h in centers],
                opponents=[h['no'] for h in opponents], additional=[h['no'] for h in extra],
                horses=horses, selection_audit=audit, sections=sections)
    from .material_display import explain_selected
    return explain_selected(insight, result, rows)
