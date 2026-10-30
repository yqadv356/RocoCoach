import base64
import xml.etree.ElementTree as ET

from rococoach.mascot import CompanionView,markup,sprite


class Area:
    def __init__(self):self.values=[]
    def html(self,value):self.values.append(value)


def test_activity_follows_actual_events_and_only_host_completion():
    area=Area();view=CompanionView(area)
    view({'type':'planning'});assert view.state=='checking'
    view({'type':'model_start'});assert view.state=='checking'
    view({'type':'draft','text':''});assert view.state=='checking'
    view({'type':'draft','text':'正在解释'});assert view.state=='speaking'
    view({'type':'validating'});assert view.state=='checking'
    view({'type':'completed'});view({'type':'executed'})
    assert view.state=='checking'  # Provider events are not commit receipts.
    view.finish('new_match');assert view.state=='complete' and '新一局已就绪' in area.values[-1]
    view.failed();assert view.state=='idle' and '这次没完成' in area.values[-1]


def test_repeated_deltas_do_not_rebuild_avatar_each_token():
    area=Area();view=CompanionView(area,motion=False)
    view({'type':'draft','text':'一'});view({'type':'draft','text':'一句'});view({'type':'draft','text':'一句话'})
    assert len(area.values)==2
    assert 'lolo-still' in area.values[-1]


def test_original_frames_are_valid_local_svg_and_status_is_accessible():
    for state in ['idle','checking','speaking','complete']:
        for frame in [0,1]:
            uri=sprite(state,frame)
            root=ET.fromstring(base64.b64decode(uri.split(',')[1]))
            assert root.attrib['viewBox']=='0 0 25 26'
            assert not any(e.tag.endswith(('script','image')) for e in root)
    html=markup(label='<img onerror="bad">',motion=False)
    assert 'role="status"' in html and 'aria-live="polite"' in html
    assert '&lt;img' in html and '<img onerror' not in html


def test_page_keeps_pet_in_chat_dock_and_motion_toggle_does_not_change_match(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from rococoach.battle import ROOT
    from rococoach.match import new_match
    from rococoach.memory import Memory
    from rococoach.llm import ModelUnavailable
    path=tmp_path/'pet.db';m=new_match();Memory(path).save_match(m)
    monkeypatch.setattr('rococoach.memory.DEFAULT_DB',path)
    def offline():raise ModelUnavailable('offline')
    monkeypatch.setattr('rococoach.llm.configuration',offline)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert not app.exception
    before=app.session_state['match']['battle']
    app.toggle(key='lolo_motion').set_value(False).run()
    assert not app.exception and app.session_state['match']['battle']==before
    assert app.session_state['match']['id']==m['id']
    app.chat_input[0].set_value('讲短一点').run()
    assert not app.exception
    assert app.session_state['match']['id']==m['id']
    assert any('先说重点' in v.value for v in app.markdown)
