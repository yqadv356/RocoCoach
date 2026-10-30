"""One whole match, guidance before each move, teaching after the result."""
from html import escape
import json
import re
import uuid
import time
from secrets import randbelow

import streamlit as st

from rococoach.battle import SCENARIOS, simulate
from rococoach.llm import ModelUnavailable, configuration
from rococoach.live_ui import LiveOutput, tool_evidence, unfinished_previews
from rococoach.answer_evidence import evidence_report,bind_legacy_reports
from rococoach.memory import Memory
from rococoach.review_jobs import review_job
from rococoach.game_ui import theme,arena
from rococoach.mascot import CompanionView,sprite as mascot_sprite,markup as mascot_markup,EVENTS as MASCOT_EVENTS
from rococoach.match import new_match, advance, outcome
from rococoach.control import apply_command,ControlConflict
from rococoach.match_coach import guide_reply, match_chat, review_match, basic_observation
from rococoach.zh import name, text, dialogue, stat_rows, matchup_rows, event_lines

st.set_page_config(page_title="洛洛 · 对战搭子",page_icon="🦊",layout="wide")
st.html(theme())
if st.session_state.get('control_notice'):st.toast(st.session_state.pop('control_notice'))
store=Memory()
try:ready=configuration()
except ModelUnavailable:ready=None


def start_match(scenario,seed,*,difficulty='standard'):
    game=new_match(scenario,seed,ruleset='short-pp-v1',difficulty=difficulty)
    store.save_match(game)
    if 'match' in st.session_state:st.session_state['mascot_notice']={'match_id':game['id'],'kind':'new_match'}
    st.session_state['match']=game


def save():store.save_match(game)


def generate_hint():
    key=str(len(game['battle']['history']))
    view=LiveOutput(live_area,[ready.model] if ready else [],activity=mascot) if mode=='live' else None
    try:
        result=guide_reply('这一回合开始了，请结合局面给一点引导，不替我选招。',game,store.summary(),mode,
                           proactive=True,**({'on_event':view} if view else {}))
        result['displayed_text']=result['reply']
        if view:result['metadata']['stream']=view.complete(result['reply'])
        game['guides'][key]=result
    except (ValueError,RuntimeError) as exc:
        if view:view.reject()
        game['guides'][key]={'error':str(exc),'metadata':{**getattr(exc,'metadata',{}),'mode':mode},
                             'rejected_output':getattr(exc,'rejected_output',None),'displayed_text':basic_observation(game)}
        game.setdefault('guide_failures',[]).append({'turn':game['battle']['turn'],**game['guides'][key]})
    live_area.empty()
    save()
    if 'error' in game['guides'][key]:mascot.failed()
    else:mascot.finish('hint')


def commit_review(result,target=None):
    target=target if target is not None else game
    target['review']=result;target.pop('review_error',None)
    if not any(m.get('kind')=='match_review' for m in target['messages']):
        target['messages'].append({'speaker':'assistant','kind':'match_review','role':'老师','text':review_text(result),'tool_report':evidence_report(result),
            'rejected_previews':result.get('metadata',{}).get('rejected_previews',[])})
    store.add(target['id']+':review','review',{'topic':target['battle']['title'],'mode':mode,
        'focus':result['answer']['focus'],'focus_status':'待下一局验证','result':result,
        'rounds':len(target['frames']),'outcome':outcome(target)})
    store.save_match(target)


def review_text(result):
    answer=result['answer']
    return answer['reply']+'\n\n下局试试：'+answer['next_practice']


def show_review(result):
    with st.chat_message('assistant'):
        st.write(dialogue(review_text(result),[ready.model] if ready else []))
        unfinished_previews(result.get('metadata',{}).get('rejected_previews',[]),expanded=False)
        tool_evidence(evidence_report(result))


def show_review_retry(current):
    with st.chat_message('assistant'):
        st.write('这局记录已经保存，详细复盘暂时没有整理好。可以继续看回合记录，或重试复盘。')
        unfinished_previews(current.get('review_previews',[]))
        if st.button('重新整理复盘',key='review_retry_'+current['id']):
            current.pop('review_error',None)
            review_job(current,store.summary(),mode,review_match,retry=True)
            store.save_match(current)


def generate_final_review():
    view=LiveOutput(live_area,[ready.model] if ready else [],activity=mascot) if mode=='live' else None
    try:
        result=review_match(game,store.summary(),mode,**({'on_event':view} if view else {}))
        if view:result['metadata']['stream']=view.complete(result['answer']['reply'])
        commit_review(result)
    except (ValueError,RuntimeError) as exc:
        if view:view.reject()
        game['review_error']=str(exc)
        if hasattr(exc,'trace'):game['failed_review_trace']=exc.trace
    live_area.empty()
    save()
    if 'review' in game:mascot.finish('review')
    else:mascot.failed()


@st.fragment(run_every=0.3)
def review_companion(match_id,motion):
    # This fragment owns the fixed header. The review-body fragment must not
    # write here: cross-fragment placeholders can vanish on the next tick.
    current=st.session_state.get('match')
    if not current or current['id']!=match_id:return
    if current.get('review'):
        state,label='complete','整局复盘已保存'
    elif current.get('review_error'):
        state,label='idle','这次没完成，记录还在'
    else:
        job=review_job(current,store.summary(),mode,review_match)
        event=job.snapshot()['event_type']
        state=MASCOT_EVENTS.get(event,'checking')
        label='正在讲解复盘' if state=='speaking' else '正在查证复盘'
    st.html(mascot_markup(state,label=label,motion=motion))


@st.fragment(run_every=0.3)
def review_progress(match_id):
    current=st.session_state.get('match')
    if not current or current['id']!=match_id:return
    # A fragment that was mounted while pending must keep rendering its final
    # message on every tick. Returning here would erase its previous elements.
    if current.get('review'):
        show_review(current['review'])
        return
    if current.get('review_error'):
        show_review_retry(current)
        return
    job=review_job(current,store.summary(),mode,review_match)
    if job.future.done():
        try:commit_review(job.future.result(),current)
        except (RuntimeError,ValueError) as exc:
            current['review_error']=str(exc)
            current['review_previews']=job.snapshot()['previews']
            if hasattr(exc,'trace'):current['failed_review_trace']=exc.trace
            store.save_match(current)
        # Render the final answer in the existing fragment, without clearing
        # the streamed message or triggering a whole-page rerun/handoff.
        if current.get('review'):
            show_review(current['review'])
        else:
            show_review_retry(current)
        return
    state=job.snapshot()
    with st.chat_message('assistant'):
        st.caption(state['status']+f" · 已等待{state['seconds']:.0f}秒")
        if state['draft']:st.markdown(dialogue(state['draft'],[ready.model] if ready else [])+' ▍')
        elif state['previews']:unfinished_previews(state['previews'])
        else:st.write(f"这局{outcome(current)}，共打了{len(current['frames'])}回合。赛果和每回合经过都已保存，我正在整理关键转折，你可以先看回放或继续聊天。")


def show_brief(value,label):
    full=dialogue(value,[ready.model] if ready else [])
    sentences=re.split(r'(?<=[。！？])',full)
    brief=''
    for sentence in sentences:
        if len(brief+sentence)>76:break
        brief+=sentence
    brief=brief or full[:76]+('…' if len(full)>76 else '')
    st.markdown('**'+label+'**')
    st.write(brief)
    if brief!=full:
        with st.popover('展开完整内容',type='tertiary'):st.write(full)
    return brief


brand,settings=st.columns([8,1],vertical_alignment='center')
with brand:
    st.html(f'<div class="brand"><img class="brand-icon" width="26" height="28" src="{mascot_sprite()}" alt=""><span class="brand-title">洛洛</span></div>')
with settings:
    with st.popover('设置',type='tertiary',icon=':material/tune:'):
        st.toggle('洛洛动作',value=True,key='lolo_motion',help='只影响动画，不改变教练回答或对局。也尊重系统的减少动态效果设置。')
        with st.expander('我的偏好'):
            profile=store.profile()
            with st.form('profile'):
                nickname=st.text_input('称呼',profile['nickname'],max_chars=30)
                preference=st.text_input('希望我怎么讲',profile['preference'],max_chars=200)
                mood=st.selectbox('心情',['平静','有点挫败','想挑战'],index=['平静','有点挫败','想挑战'].index(profile['mood']))
                if st.form_submit_button('保存偏好'):
                    store.save_profile(nickname,preference,mood);st.success('已保存。')
        with st.expander('对局设置'):
            scenario=st.selectbox('场景',list(SCENARIOS),format_func=lambda s:text(SCENARIOS[s]),key='match_scenario')
            if st.button('开始新对局'):
                try:start_match(scenario,randbelow(65536));st.rerun()
                except (RuntimeError,ValueError) as exc:st.error(str(exc))
        with st.expander('学习记录与回答依据'):
            st.caption('一局由多个回合组成：每回合先观察、自己选招，分出胜负后才做整局教师复盘。')
            st.caption('局中提示只读取公开状态，不读取伤害排名、独立分支或对手下一招。完整计算与关键回合证据在赛后开放。')
            st.caption('本局全部回合和选择理由保存在本机，刷新可恢复最近一局。近期聊天窗口最多6轮，赛后工具教练最多4轮；复盘工具可读取整局，不靠聊天窗口记住全部战况。')
            st.caption('明确偏好与最近5条学习摘要单独保存；逐回合事件不会挤掉学习摘要，没有自动提炼长期偏好或生产级多用户隔离。')
            for item in store.summary()['recent'][:3]:st.caption(text(item['topic']))
            previous=st.session_state.get('match') or store.latest_match()
            if previous:
                st.caption(f"本局已完成 {len(previous['frames'])} 回合 · {outcome(previous)}")
                if previous['battle']['ended'] or previous['battle']['capped']:
                    if previous.get('review'):
                        st.json(previous['review'],expanded=False)
                    if previous.get('last_chat',{}).get('metadata',{}).get('agent'):
                        st.json(previous['last_chat']['metadata']['agent'],expanded=False)
                    if previous.get('failed_review_trace'):st.json(previous['failed_review_trace'],expanded=False)
                    if previous.get('guide_failures'):st.json({'未通过的局中提示':previous['guide_failures']},expanded=False)
                    st.download_button('导出整局记录',json.dumps(previous,ensure_ascii=False,indent=2),'整局学习记录.json',mime='application/json')
                else:st.caption('局中不展示逐招评分或未核验草稿，避免把思考题变成答案表。')
        with st.expander('模型与隐私'):
            mode_label=st.radio('回答来源',['智能教练','离线演示'],index=0 if ready else 1,key='match_mode')
            st.caption('局中发送公开状态、近期对话与明确记忆，隐藏招式排名和对手未来行动；赛后可发送整局记录、理由与计算证据。数据保存在本机。')
mode='live' if mode_label=='智能教练' else 'mock'
if mode=='mock':st.caption('离线演示 · 提示和复盘来自规则模板')
st.html('<div class="top-line"></div>')
if 'match' not in st.session_state:
    try:
        restored=store.latest_match()
        if restored and restored.get('version')=='full-match-v1':st.session_state['match']=restored
        else:start_match('practice',42)
    except (RuntimeError,ValueError) as exc:st.error(str(exc));st.stop()
game=st.session_state['match'];battle=game['battle']
finished=battle['ended'] or battle['capped']
with st.container(key='game_workspace'):
    board,conversation=st.columns([1.15,1],gap='large')
    with conversation:
        chat_dock=st.container(key='chat_dock')
        with chat_dock:
            motion=st.session_state.get('lolo_motion',True)
            background_review=finished and mode=='live' and 'review' not in game and 'review_error' not in game
            if background_review:
                review_companion(game['id'],motion)
                mascot=CompanionView(None,motion=motion)
            else:mascot=CompanionView(st.empty(),motion=motion)
            transcript=st.container(height=620,border=False,autoscroll=True,key='chat_log')
            live_area=transcript.empty()
    notice=st.session_state.pop('mascot_notice',None)
    if notice and notice['match_id']==game['id']:mascot.finish(notice['kind'])

    with board:
        with st.container(border=True,key='practice_card'):
            st.html(f'<div class="scene-title">{"本局结束，回头看一看。" if finished else "第 "+str(battle["turn"])+" 回合，你来决定。"}</div>')
            if finished:st.caption(outcome(game))
            st.html(arena(battle))
            if battle.get('difficulty')=='challenge':st.caption('进阶对练 · 对手会评估当前公开局面后出招')
            if not finished:
                key=str(len(battle['history']))
                hint=game['guides'].get(key)
                if hint is None or hint.get('metadata',{}).get('mode')!=mode:
                    generate_hint();hint=game['guides'][key]
                original=hint.get('reply') or hint.setdefault('full_observation',hint.get('displayed_text') or basic_observation(game))
                visible=show_brief(original,'洛洛提醒')
                hint['displayed_text']=visible
                if 'error' in hint:st.caption('基础观察')
                moves=sorted((m for m in battle['advice'] if not m['disabled']),key=lambda m:m['choice'])
                with st.form('decision_'+game['id']+'_'+key):
                    pick,thought=st.columns([1,1],vertical_alignment='bottom')
                    with pick:
                        labels={m['choice']:name(m['name'])+(f" · 剩{m['pp']}/{m['maxPp']}次" if m.get('maxPp') is not None else f" · 剩{m['pp']}次" if m.get('pp') is not None else ' · 应急招式，会反伤') for m in moves}
                        choice=st.selectbox('这回合用哪招',[m['choice'] for m in moves],format_func=labels.get,label_visibility='collapsed')
                    with thought:
                        reason=st.text_input('你的想法',placeholder='想法（可不填）',max_chars=1000,label_visibility='collapsed')
                    execute=st.form_submit_button('出招',type='primary',width='stretch')
                if game.get('turn_error'):st.error(game['turn_error'])
                if execute:
                    try:
                        updated=advance(game,choice,reason,expected_round=len(battle['history']))
                        updated.pop('turn_error',None)
                        store.save_match(updated)
                        frame=updated['frames'][-1]
                        store.add(updated['id']+':turn:'+str(frame['turn']),'turn',{'topic':battle['title'],'turn':frame['turn'],
                            'reason':frame['reason'],'actual':frame['actual'],'mode':mode})
                        st.session_state['match']=updated;st.rerun()
                    except (RuntimeError,ValueError) as exc:game['turn_error']=str(exc);save();st.rerun()
            else:
                if mode=='mock' and 'review' not in game and 'review_error' not in game:generate_final_review()
                if 'review' in game:
                    answer=game['review']['answer']
                    show_brief(answer['next_practice'],'下局试试')
                    st.caption('洛洛的整局复盘在右侧，可以接着问。')
                elif game.get('review_error'):
                    st.caption('对局已完整保存，教师复盘暂未完成。重试不会再执行任何回合。')
                    if st.button('重试整局复盘',type='primary',width='stretch'):
                        if mode=='mock':generate_final_review()
                        else:
                            game.pop('review_error',None);review_job(game,store.summary(),mode,review_match,retry=True);save()
                        st.rerun()
                if 'review' not in game and 'review_error' not in game:st.caption('赛果已保存，整局复盘在右侧；可以看回放或接着聊。')
                if st.button('再来一局',type='primary',width='stretch'):
                    try:start_match(battle['scenario'],randbelow(65536),difficulty=battle.get('difficulty','standard'));st.rerun()
                    except (RuntimeError,ValueError) as exc:st.error(str(exc))
            handbook,history=st.columns(2)
            with handbook:
                with st.popover('招式与规则',width='stretch'):
                    st.caption('先看属性与状态，再结合命中风险和行动顺序，决定这一回合的节奏。')
                    st.write('物理招式看攻击与防御，特殊招式看特攻与特防。属性克制、本系加成和威力共同影响伤害；威力不等于扣血。通常先比优先度、再比速度，标称命中也不是无条件保证。')
                    shown=battle if not finished else game['frames'][-1]['before']
                    st.caption('当前公开招式资料；赛后回看的是最后一回合出招前。')
                    st.caption('短局训练：每招只有1–4次，双方相同。实际发动后消耗，未命中也会消耗；用完不能再选，全部耗尽则只能挣扎并承受反伤。新一局恢复。' if battle.get('ruleset')=='short-pp-v1' else '本局沿用原有次数规则；开始新对局后使用短局次数。')
                    st.table([{'招式':name(m['name']),'类别':name(m['category']),'属性':name(m['type']),
                               '威力':m['power'],'标称命中':f"{m['accuracy']}%",'剩余/上限':f"{m['pp']}/{m.get('maxPp','—')}" if m.get('pp') is not None else '应急招式', '可用':'已用尽' if m['disabled'] else '可选'} for m in sorted(shown['advice'],key=lambda m:m['choice'])])
                    for label,mon in [('你的伙伴',shown['player']),('对手',shown['opponent'])]:
                        st.caption(label+' · '+name(mon['name'])+' · 面板能力（未叠加能力等级变化）');st.table(stat_rows(mon))
                    if finished:
                        st.caption('赛后数值核对：伤害区间已计入属性等机制，不要重复乘倍率。比较分值只评价直接伤害，不含先手、控制和对手后续策略的完整价值。')
                        st.table(matchup_rows(shown))
            with history:
                with st.popover('回合记录',width='stretch'):
                    if game['frames']:
                        st.caption('最近一回合')
                        for line in event_lines(game['frames'][-1]['actual']['events']):st.write(line)
                        st.table([{'回合':f['turn'],'你的选择':name(f['actual']['selected']),
                                   '你的生命':f"{f['actual']['playerHpBefore']} → {f['actual']['playerHpAfter']}",
                                   '对手生命':f"{f['actual']['opponentHpBefore']} → {f['actual']['opponentHpAfter']}",
                                   '当时理由':f['reason'] or '未填写'} for f in game['frames']])
                    else:st.caption('出招后，这里会记录每回合的经过。')
    
    with conversation:
        with chat_dock:
            bind_legacy_reports(game)
            with transcript:
                if not game['messages']:
                    with st.chat_message('assistant'):st.write('这局咱们慢慢打。拿不准时一起想，也可以随时聊点轻松的。')
                for item in game['messages']:
                    with st.chat_message(item['speaker']):
                        if item.get('correction'):st.caption(item['correction'])
                        if item.get('kind')=='basic_observation':st.caption('基础观察')
                        st.write(dialogue(item['text'],[ready.model] if ready else []))
                        if item.get('status') in {'failed','generating'}:
                            if item.get('status')=='generating':st.caption('这条回答尚未完成；已展示的草稿保留在下方。')
                            unfinished_previews(item.get('previews',[]))
                        elif item.get('revision_count'):
                            unfinished_previews([p for p in item.get('previews',[]) if p!=dialogue(item['text'])],expanded=False)
                        if item.get('rejected_previews'):unfinished_previews(item['rejected_previews'],expanded=False)
                        if finished and item['speaker']=='assistant' and item.get('kind') in {'chat','match_review'}:
                            if 'tool_report' in item:
                                tool_evidence(item['tool_report'])
        
        
                if finished and mode=='live' and 'review' not in game and 'review_error' not in game:review_progress(game['id'])
            typed=st.chat_input('聊聊这局，也可以说“再来一局”“讲短一点”',max_chars=500,key='coach_query')
            if typed:
                view=None
                request_id=uuid.uuid4().hex
                response={'speaker':'assistant','text':'正在整理这条回答。','kind':'chat_pending','status':'generating','request_id':request_id,'previews':[]}
                game['messages'].extend([{'speaker':'user','text':typed,'kind':'chat','request_id':request_id},response])
                save()
                checkpoint={'at':0}
                with transcript:
                    with st.chat_message('user'):st.write(typed)
                    if mode=='live':view=LiveOutput(st.chat_message('assistant'),[ready.model] if ready else [],activity=mascot)
                def receive(event):
                    view(event)
                    if event['type'] in {'draft','revision'} and (time.monotonic()-checkpoint['at']>=0.5 or event['type']=='revision'):
                        preview=view.snapshot()
                        response.update({'previews':preview['previews'],'revision_count':preview['revision_count']})
                        save();checkpoint['at']=time.monotonic()
                try:
                    result=match_chat(typed,game,store.summary(),mode,**({'on_event':receive} if view else {}))
                    if result.get('clear_pending'):game.pop('pending_action',None)
                    if result.get('proposal'):
                        game['pending_action']=result['proposal'];response['proposal_id']=result['proposal']['id']
                    elif not result.get('command'):game.pop('pending_action',None)
                    if result.get('command'):
                        try:updated,result=apply_command(store,game,result,typed,request_id)
                        except ControlConflict as exc:
                            st.session_state['match']=store.latest_match()
                            st.session_state['control_notice']=str(exc)
                            st.rerun()
                        if view:view.complete(result['reply'])
                        st.session_state['match']=updated
                        st.session_state['mascot_notice']={'match_id':updated['id'],'kind':'new_match' if result['execution']['tool']=='start_new_match' else 'style'}
                        st.rerun()
                    if view:result['metadata']['stream']=view.complete(result['reply'])
                    else:
                        with transcript:
                            with st.chat_message('assistant'):
                                st.write(dialogue(result['reply']))
                                if finished:tool_evidence(evidence_report(result))
                    response.update({'text':result['reply'],'kind':'chat','status':'completed','role':result['role'],'tool_report':evidence_report(result)})
                    if view:
                        preview=view.snapshot();response.update({'previews':preview['previews'],'revision_count':preview['revision_count']})
                    game['last_chat']=result;game.pop('chat_error',None)
                    store.add(uuid.uuid4().hex,'chat',{'topic':'整局陪练','user':typed,'assistant':result['reply'],
                        'role':result['role'],'mode':mode,'metadata':result['metadata'],'routing':result['routing']})
                    save()
                    mascot.finish('chat')
                    if view and finished:
                        with view.target:tool_evidence(evidence_report(result))
                    if view and response.get('revision_count'):
                        with view.target:
                            unfinished_previews([p for p in response.get('previews',[]) if p!=dialogue(result['reply'])],expanded=False)
                except (RuntimeError,ValueError) as exc:
                    if view:
                        response['previews']=view.snapshot()['previews']
                    game.setdefault('chat_failures',[]).append({'request_id':request_id,'query':typed,'turn':battle['turn'],'error':str(exc),
                        'rejected_output':getattr(exc,'rejected_output',None),'metadata':getattr(exc,'metadata',{})})
                    errors=' '.join(t.get('validation_error','') for t in getattr(exc,'trace',[]))+' '+str(exc)
                    reason='刚才的内容与当前对局对不上，未通过核对。' if '宠物' in errors or '场景' in errors else '这条回答没有完成生成或核对。'
                    response.update({'text':reason+' 已展示的草稿保留在下方，暂不作为正式建议。你的输入和对局记录都还在。',
                        'kind':'chat_failed','status':'failed','response_source':'program'})
                    if view:
                        view.failed(response['text'])
                        if len(response['previews'])>1:
                            with view.target:unfinished_previews(response['previews'],expanded=False)
                    else:
                        with transcript:
                            with st.chat_message('assistant'):st.write(response['text'])
                    game.pop('chat_error',None);save();mascot.failed()
            if game.get('chat_error'):
                with st.chat_message('assistant'):
                    st.write(basic_observation(game) if not finished else '这部分先放一放，已经发生的回合都留在整局回放里。')
                    st.caption('基础观察')

st.html('<div class="footer-note">洛洛陪你打，也陪你聊</div>')
