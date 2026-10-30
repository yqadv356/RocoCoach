"""Original code-drawn coach companion; host events, never model emotion guesses."""
from base64 import b64encode
from functools import lru_cache
from html import escape


LABELS={'idle':'陪你慢慢练','checking':'正在查证','speaking':'正在讲解','complete':'这条回答已完成'}
FINISH={'hint':'观察方向已准备好','chat':'这条回答已完成','review':'整局复盘已保存',
        'new_match':'新一局已就绪','style':'表达偏好已更新'}
# Four visual states. Failure returns to a calm pose with an honest status;
# a provider delta can never authorize the completed state.
EVENTS={'planning':'checking','model_start':'checking','tool':'checking',
        'revision':'checking','validating':'checking','draft':'speaking'}


@lru_cache(maxsize=8)
def sprite(state='idle',frame=0):
    if state not in LABELS or frame not in {0,1}:raise ValueError('Unknown companion frame')
    palette={'O':'#191e36','P':'#b9a9ed','L':'#dfd5ff','S':'#8c7bc0','G':'#f0cc78','C':'#77cbbb'}
    # An original 24x26 notebook spirit with a scarf and a star antenna.
    rows=[
      '           GG           ',
      '          GGGG          ',
      '           GG           ',
      '           OO           ',
      '      OOOOOPPOOOOO      ',
      '     OLLLPPPPPPPPLO     ',
      '    OLLPPPPPPPPPPPLO    ',
      '   OLLPPPPPPPPPPPPPSO   ',
      '   OLPPPPPPPPPPPPPPSO   ',
      '   OPPPPPPPPPPPPPPPSO   ',
      '   OPPPPPPPPPPPPPPPSO   ',
      '   OPPPPPPPPPPPPPPPSO   ',
      '   OPPPPPPPPPPPPPPPSO   ',
      '    OPPPPPPPPPPPPSSO    ',
      '     OOPPPPPPPSSSOO     ',
      '      OGGGGGGGGGO       ',
      '     OPGGGGGGGGGPO      ',
      '    OPPPPOGGOPPPPPO     ',
      '    OPPPPOGGOPPPPSO     ',
      '    OPPPPPPPPPPSSSO     ',
      '     OPPPPPPPPSSSO      ',
      '      OOPPOOPPOOO       ',
      '      OPPPOOPPPO        ',
      '       OOO  OOO         ',
    ]
    elements=[f'<rect x="{x}" y="{y}" width="1" height="1" fill="{palette[c]}"/>'
              for y,row in enumerate(rows) for x,c in enumerate(row) if c in palette]
    def rect(x,y,w,h,color):elements.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>')
    # Face: calm eyes, a blink, or a smile. Cheeks remain subtle.
    for x in [7,15]:
        if state=='complete':
            rect(x,9,2,1,'#24233f');rect(x-1,10,1,1,'#24233f');rect(x+2,10,1,1,'#24233f')
        else:rect(x,10,2,1 if frame else 2,'#24233f')
    rect(5,12,2,1,'#77cbbb');rect(17,12,2,1,'#77cbbb')
    rect(11,13,2,1 if state!='speaking' or frame else 2,'#584a7d')
    # The notebook changes pose with evidence work, not with guessed feelings.
    rect(10,17,10,6,'#191e36');rect(11,17,4,5,'#f3e7c8');rect(15,17,4,5,'#ded6c0')
    rect(15,17,1,5,'#b6a58e');rect(12,18,2,1,'#8b92ab');rect(16,18,2,1,'#8b92ab')
    rect(9,19,2,2,'#b9a9ed');rect(19,19,2,2,'#b9a9ed')
    if state=='checking':
        rect(16 if frame else 12,20,2,1,'#8b92ab')
        rect(21,8,2,2,'#f0cc78');rect(20,9,4,1,'#f0cc78')
    if state=='speaking':
        rect(20,4,4,4,'#f4edda');rect(19,7,2,2,'#f4edda');rect(21,5,1,1,'#51476b')
    if state=='complete':
        rect(20,4,2,1,'#77cbbb');rect(21,3,2,1,'#77cbbb');rect(22,2,2,1,'#77cbbb')
        rect(19,3,1,1,'#77cbbb')
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 26" shape-rendering="crispEdges">'+''.join(elements)+'</svg>'
    return 'data:image/svg+xml;base64,'+b64encode(svg.encode()).decode()


def markup(state='idle',*,label=None,motion=True):
    if state not in LABELS:raise ValueError('Unknown companion state')
    label=label or LABELS[state]
    classes=f'lolo-companion lolo-{state}'+(' lolo-still' if not motion else '')
    return f'''<div class="{classes}" data-lolo-state="{state}" role="status" aria-live="polite" aria-atomic="true">
    <span class="lolo-sprite" aria-hidden="true"><img class="lolo-frame lolo-frame-a" src="{sprite(state,0)}" alt=""><img class="lolo-frame lolo-frame-b" src="{sprite(state,1)}" alt=""></span>
    <span class="lolo-identity"><strong>洛洛</strong><span>{escape(label)}</span></span></div>'''


class CompanionView:
    def __init__(self,target,*,motion=True):
        self.target=target;self.motion=motion;self.current=None;self.state='idle';self.render('idle')

    def render(self,state,label=None):
        label=label or LABELS[state]
        if self.current==(state,label):return
        if self.target is not None:self.target.html(markup(state,label=label,motion=self.motion))
        self.current=(state,label);self.state=state

    def __call__(self,event):
        state=EVENTS.get(event.get('type'))
        if state and (event.get('type')!='draft' or event.get('text')):self.render(state)

    def finish(self,kind):
        # Called by the host AFTER storing/committing the corresponding result.
        self.render('complete',FINISH[kind])

    def failed(self):self.render('idle','这次没完成，记录还在')
