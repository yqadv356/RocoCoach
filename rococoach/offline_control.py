"""Finite rule-only offline demonstration. Never used for live language routing."""
from copy import deepcopy
import json
import re
import time
from rococoach.agent import Environment,Empty
from rococoach.battle import SCENARIOS
from rococoach.companion import Reply
from rococoach.control import NewGame,ResponseStyle,token
from rococoach.match_tools import digest


TOOLS={
    'inspect_session':('读取当前是否结束、当前场景和表达偏好；这是事实，不是操作授权。',Empty),
    'start_new_match':('仅当用户当前消息明确要求重新开始/再打一局/换场景时，准备新对局；保留旧局，不代打，不改变招式资源规则。same表示沿用场景。',NewGame),
    'propose_new_match':('仅在玩家需要建议而未明确要求马上开局时，提出结构化开局方案，等待下一句确认；不能用文字询问代替调用此工具。',NewGame),
    'set_response_style':('仅当用户当前消息明确要求改变讲解风格时，准备保存简洁/详细/引导式偏好。不能据历史或模型推测自动修改。',ResponseStyle),
}


NEW_REQUEST=r'重开|重来|重新(?:开始|开局|开一局|打一局)|再(?:来|打|开|试).{0,12}(?:次|局|把)|换.{0,8}(?:场景|对手|对练)'


def confirmation(query):return re.sub(r'[\s，。！？!?,.]+','',query) in {'好','好的','可以','行','同意','开始吧','开吧','就这样','没问题'}


def pending_action(match):
    pending=match.get('pending_action')
    if pending:
        relevant=[m for m in match.get('messages',[]) if m.get('speaker')=='assistant' and m.get('kind') in {'chat','control'} and m.get('status') not in {'generating','failed'}]
        if relevant and relevant[-1].get('proposal_id')!=pending['id']:return None
        return deepcopy(pending)
    # Compatibility for earlier versions that asked an unstructured question.
    # Current affirmative input supplies consent; old text is only its referent.
    rows=[m for m in match.get('messages',[]) if m.get('kind') not in {'chat_pending','chat_failed'}]
    assistants=[m for m in rows if m.get('speaker')=='assistant' and m.get('kind') in {'chat','control'}]
    if not assistants:return None
    last=assistants[-1];offer=last.get('text','')
    if last.get('kind')!='chat' or not re.search(r'(要我|需要我).{0,25}(开|开始).{0,20}局',offer) or not re.search(r'[吗？?]',offer[-100:]):return None
    requests=[m.get('text','') for m in rows if m.get('speaker')=='user'][-6:]
    original=next((q for q in reversed(requests) if re.search(NEW_REQUEST,q)),None)
    if not original:return None
    pairs={'fire':('喷火龙','妙蛙花'),'electric':('皮卡丘','杰尼龟'),'water':('水箭龟','喷火龙'),'practice':('杰尼龟','杰尼龟')}
    scene=next((s for s,pair in pairs.items() if all(n in offer for n in pair)),None)
    if scene is None:return None
    args={'scenario':scene,'difficulty':'challenge' if re.search(r'难|挑战',original) else 'same'}
    return {'id':digest({'offer':offer,'source':token(match)}),'arguments':args,'source_token':token(match),
            'expires_at':time.time()+300,'origin':'legacy_offer','original_query':original}


def candidate(query):
    if re.search(r'解释|重讲|复盘|重放|讲解',query) and not re.search(r'重开|新开|再打|再开|简[短洁]|详细|引导|短一点',query):
        return False
    return bool(re.search(NEW_REQUEST+r'|(?:讲|说|解释|回复|回答).{0,8}(?:简[短洁]|详细|引导|短一点)|(?:简[短洁]|详细|引导).{0,6}(?:讲|说|解释|回复|回答)',query))


class ControlEnvironment(Environment):
    def __init__(self,match,memory,query,confirmed=None):
        super().__init__(match['battle'],memory)
        self.match=match;self.query=query;self.command=None;self.proposal=None;self.confirmed=confirmed
    def available(self):return list(TOOLS)
    def specs(self):
        return [{'type':'function','function':{'name':n,'description':d,'parameters':s.model_json_schema()}} for n,(d,s) in TOOLS.items()]
    def execute(self,tool,raw):
        started=time.monotonic()
        if tool not in TOOLS:raise ValueError('不支持的操作。')
        args=TOOLS[tool][1].model_validate_json(raw)
        if tool=='inspect_session':
            data={'场景':SCENARIOS[self.battle['scenario']],'场景ID':self.battle['scenario'],
                  '当前训练档位':self.battle.get('difficulty','standard'),
                  '已结束':self.battle['ended'] or self.battle['capped'],'已完成回合':len(self.battle['history']),
                  '可选场景':SCENARIOS,'训练档位':{'standard':'随机对手','challenge':'按当前公开局面评估直接伤害和命中选择招式；不是全局最优AI，不偷看玩家行动'},
                  '偏好':self.memory.get('profile',{}).get('preference','简洁')}
        else:
            # Negated, hypothetical and quoted commands are not execution requests.
            # Semantic selection belongs to the model; this additional gate fails closed.
            if re.search(r'不要|别(?:给我)?|不用|不想|如果|假如|比如|例如|怎么实现|如何实现|能做什么|[“「『"\']',self.query):
                raise ValueError('当前消息不能作为直接执行授权，请只提出你要执行的操作。')
            if self.command is not None or self.proposal is not None:raise ValueError('每条消息只处理一个操作。')
            if tool=='propose_new_match':
                if re.search(NEW_REQUEST,self.query) and not re.search(r'推荐|建议|先看看|先选|比较|有哪些',self.query):
                    raise ValueError('玩家已明确要求开局，请使用start_new_match，不要再次询问。')
                self.proposal={'id':digest({'args':args.model_dump(),'source':token(self.match),'time':time.time()}),
                    'arguments':args.model_dump(),'source_token':token(self.match),'expires_at':time.time()+300,'origin':'typed_tool'}
                data={'状态':'等待玩家确认','方案':self.proposal}
                return {'evidence':[self.fact('control:'+tool,data,'结构化待确认方案')]}
            if tool=='start_new_match':
                confirmed=self.confirmed is not None
                if confirmed and args.model_dump()!=self.confirmed['arguments']:raise ValueError('确认参数与待执行方案不一致。')
                if not confirmed and not re.search(NEW_REQUEST,self.query):
                    raise ValueError('当前消息没有要求新对局。')
                if re.search(r'解释|重讲|复盘|重放|讲解',self.query) and not re.search(r'重开|新开|再打|再开',self.query):
                    raise ValueError('这是讲解或回放请求，不会重开对局。')
                # During play, vague "again" could refer to a previous hint.
                if not confirmed and not(self.battle['ended'] or self.battle['capped']) and not re.search(r'重开|重来|重新(?:开始|开局|开一局|打一局)|再(?:来|打|开).{0,12}(?:局|把)|换.{0,8}(?:场景|对手|对练)',self.query):
                    raise ValueError('这局还没结束，请明确说重开一局，或说明想再看哪段内容。')
                aliases={'practice':['均衡','镜像','杰尼龟对杰尼龟'],
                         'electric':['皮卡丘','电系'],'fire':['妙蛙花','火系'],'water':['水箭龟','水系']}
                harder=bool(re.search(r'难|挑战|进阶',self.query))
                if not confirmed and harder:
                    args=args.model_copy(update={'difficulty':'challenge','scenario':'practice' if args.scenario=='same' else args.scenario})
                if not confirmed and re.search(r'简单|轻松|容易',self.query):args=args.model_copy(update={'difficulty':'standard'})
                if not confirmed and not harder and args.difficulty not in {'same',self.battle.get('difficulty','standard')} and not re.search(r'简单|轻松|容易',self.query):
                    raise ValueError('没有请求改变训练档位。')
                if not confirmed and args.scenario!='same' and not (harder and args.scenario=='practice') and not any(a in self.query for a in aliases[args.scenario]):
                    raise ValueError('没有明确指定这个场景，请说明想练哪一组对手。')
                if '换' in self.query and args.scenario=='same':raise ValueError('想换哪组对手？可以说换成皮卡丘场景，或换成水箭龟场景。')
            else:
                if not re.search(r'(?:讲|说|解释|回复|回答)',self.query):raise ValueError('没有明确要求改变讲解风格。')
                signals={'简洁':r'简短|简洁|短一点|讲短|说短','详细':r'详细','引导式':r'引导'}
                if not re.search(signals[args.style],self.query):raise ValueError('讲解风格与当前请求不一致。')
            self.command={'tool':tool,'arguments':args.model_dump(),'source_token':token(self.match),'query_hash':digest(self.query)}
            if self.confirmed:
                self.command['proposal_id']=self.confirmed['id'];self.command['confirmation_origin']=self.confirmed.get('origin')
            data={'状态':'已准备，尚未执行','操作':tool,'参数':args.model_dump()}
        fact=self.fact('control:'+tool,data,'本机对话操作工具')
        return {'evidence':[fact],'receipt':{'version':'control-tools-v1','tool':tool,'phase':'observed' if tool=='inspect_session' else 'prepared',
            'arguments':args.model_dump(),'input_hash':token(self.match),'output_hash':digest(data),
            'match_unchanged':True,'elapsed_seconds':round(time.monotonic()-started,4)}}


def offline_control_reply(query,match,memory,mode='mock'):
    """Explicit rule demonstration only. Never used for live intent recognition."""
    pending=pending_action(match)
    if pending and re.fullmatch(r'(取消|算了|不用了|不要了)[。！!\s]*',query):
        return {'reply':'好，这个开局方案已取消。','role':'陪聊','routing':{},'metadata':{'mode':mode},'command':None,'clear_pending':True}
    if pending and confirmation(query):
        if pending['source_token']!=token(match) or pending['expires_at']<time.time():
            return {'reply':'当前局面已变化或方案已过期，请重新说一下想开的对局。','role':'陪聊','routing':{},'metadata':{'mode':mode},'command':None,'clear_pending':True}
        env=ControlEnvironment(match,memory,query,confirmed=pending)
        env.execute('start_new_match',json.dumps(pending['arguments']))
        return {'reply':'正在按确认的方案开局。','role':'陪聊','routing':{},'metadata':{'mode':mode,'answer_source':'confirmed_pending_action'},'command':env.command}
    if not candidate(query):return None
    env=ControlEnvironment(match,memory,query)
    if mode=='mock':
        env.execute('inspect_session','{}')
        try:
            if re.search(r'简[短洁]|详细|引导|短一点',query) and re.search(r'讲|说|解释|回复|回答',query):
                style='详细' if '详细' in query else '引导式' if '引导' in query else '简洁'
                env.execute('set_response_style',json.dumps({'style':style}))
            else:
                scene=next((s for s,label in [('electric','皮卡丘'),('fire','妙蛙花'),('water','水箭龟'),('practice','均衡')] if label in query),'same')
                env.execute('start_new_match',json.dumps({'scenario':scene}))
            answer=Reply(reply='操作已准备，正在交给训练场执行。',evidence_ids=list(env.seen),suggested_choice=None)
        except ValueError as exc:
            answer=Reply(reply=str(exc),evidence_ids=['control:inspect_session'],suggested_choice=None)
        meta={'mode':'mock','model':'deterministic-control-demo','agent':{'trace':[]}}
    else:raise ValueError('不支持的模式。')
    if env.command is None and env.proposal is None and re.search(NEW_REQUEST,query):
        try:
            env.execute('start_new_match',json.dumps({'scenario':'same'}))
            meta['execution_selection']='host_fallback_for_explicit_request'
        except ValueError:pass
    reply=answer.reply
    if env.proposal:
        args=env.proposal['arguments'];scene=match['battle']['scenario'] if args['scenario']=='same' else args['scenario']
        reply='我可以开一局'+SCENARIOS[scene]+('，使用进阶对手。' if args['difficulty']=='challenge' else '。')+'现在开始吗？'
    return {'reply':reply,'role':'陪聊','routing':{'role':'陪聊','context_source':'conversation_control'},
            'metadata':meta,'evidence_ids':answer.evidence_ids,'command':deepcopy(env.command),'proposal':deepcopy(env.proposal)}
