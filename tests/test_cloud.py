import hashlib, sqlite3, sys, types, os
from pathlib import Path
from contextlib import closing
import pytest
from pmo.cloud_runtime import prepare, reset, SEED, KEY
from pmo import config, clients, matrix, v5_engine, step2
from pmo.alpha_navigation import STEPS, VERSION
from build_demo_seed import init
ROOT=Path(__file__).resolve().parents[1]

def hash_file(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def test_seed():
    with closing(sqlite3.connect(SEED)) as c:
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        assert c.execute('select count(*) from pmo_clientes').fetchone()[0]==6
        assert c.execute("select count(*) from pmo_clientes where nombre like 'Cliente ficticio %' and correo is null").fetchone()[0]==6
        assert c.execute('select count(*) from p2_expectativas').fetchone()[0]==30
        assert c.execute('select count(*) from p2_necesidades').fetchone()[0]==6
        assert c.execute("select count(*) from p4_services where estado='Borrador'").fetchone()[0]==2
        assert c.execute('select count(*) from p1_eventos').fetchone()[0]==2
        assert c.execute('select count(*) from p2_madurez_preguntas_fuentes').fetchone()[0]==0

def test_sessions_and_reset(monkeypatch,tmp_path):
    a,b={},{}; before=hash_file(SEED)
    try:
        p1,p2=prepare(a),prepare(b);assert p1!=p2
        fake=types.SimpleNamespace(session_state=a);monkeypatch.setitem(sys.modules,'streamlit',fake)
        monkeypatch.setenv('PMO_CENS_DATA_DIR',str(tmp_path/'must-not-use'))
        assert config.data_dir()==p1
        clients.create_client({'codigo':'DEMO-NEW','nombre':'Prueba aislada','dependencia':'DEMO'},'Laboratorio')
        assert len(clients.list_clients())==7
        assert prepare(a)==p1
        fake.session_state=b; assert config.data_dir()==p2;assert len(clients.list_clients())==6
        assert not (tmp_path/'must-not-use').exists()
        reset(a);assert not p1.exists();assert not a
        fake.session_state=a
        with pytest.raises(RuntimeError):config.data_dir()
        p3=prepare(a);assert p3!=p1 and len(clients.list_clients())==6
        assert hash_file(SEED)==before
    finally:reset(a);reset(b)

def test_initializers_idempotent():
    state={}
    try:
        db=prepare(state)/'pmo_flywheel.sqlite3';init(db);init(db)
        with closing(sqlite3.connect(db)) as c:
            assert c.execute('select count(*) from pmo_clientes').fetchone()[0]==6
            assert c.execute('select count(*) from p2_expectativas').fetchone()[0]==30
            assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
            assert not c.execute('pragma foreign_key_check').fetchall()
    finally:reset(state)

def test_cloud_scope():
    assert len(STEPS)==10 and 'Cloud' in VERSION
    assert not (ROOT/'datos_iniciales').exists() and not (ROOT/'workshop_assets').exists()
    assert not (ROOT/'pmo/data/escenarios_v5_38.json').exists()
    assert len(list(ROOT.rglob('*.sqlite3')))==1
    assert not list(ROOT.rglob('*.pdf'))
    assert not list(ROOT.rglob('*.bat'))

def test_v5_run_is_local_to_demo():
    a,b={},{}; before=hash_file(SEED)
    try:
        db=prepare(a)/'pmo_flywheel.sqlite3'; other=prepare(b)/'pmo_flywheel.sqlite3'
        with closing(sqlite3.connect(db)) as c:diag=c.execute('select id from p2_diagnosticos').fetchone()[0]
        run=step2.run(diag,{'Dirección de ensayo':60,'Equipo de ensayo':40},'Laboratorio ficticio',path=db,matrix_version_id=matrix.V5_ID)
        result=step2.get_run(run,path=db)['resultados'];assert result['participants']==6
        assert len(result['services'])==26
        assert result['v5_validation']['matrix_sha256']==matrix.V5_HASH
        assert len(step2.runs(diag,path=other))==0 and hash_file(SEED)==before
    finally:reset(a);reset(b)

def test_every_sidebar_component_dispatches(monkeypatch):
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    from contextlib import nullcontext
    stub=MagicMock()
    stub.dialog.side_effect=lambda *a,**kw: (lambda f:f)
    monkeypatch.setitem(sys.modules,'streamlit',stub)
    monkeypatch.setitem(sys.modules,'streamlit.components',stub.components)
    monkeypatch.setitem(sys.modules,'streamlit.components.v1',stub.components.v1)
    from pmo.alpha_navigation import HOME
    import pmo.ui as ui
    from pmo import alpha02_sidebar as native
    from pmo import step2_ui,step3_ui,step4_ui,step5_ui,step6_ui,step7_ui,step8_ui,step9_ui,step10_ui
    modules=[ui,step2_ui,step3_ui,step4_ui,step5_ui,step6_ui,step7_ui,step8_ui,step9_ui,step10_ui]
    state={};calls=[]
    mock=SimpleNamespace(session_state=state,sidebar=nullcontext(),container=lambda **kw:nullcontext(),
         expander=lambda *a,**kw:nullcontext(),markdown=lambda *a,**kw:None,caption=lambda *a,**kw:None,
         button=lambda label,**kw:calls.append((label,kw)))
    monkeypatch.setitem(sys.modules,'streamlit',mock);monkeypatch.setattr(ui,'st',mock)
    # Decorator/widget style helpers tested elsewhere; exercise the actual sidebar router and native callbacks.
    import pmo.panel_layout as panel,pmo.design_system as ds
    for name in ('apply_panel_theme','render_sidebar_branding','render_section_heading','render_component_heading','render_sidebar_footers'):
        monkeypatch.setattr(panel,name,lambda *a,**kw:None)
    monkeypatch.setattr(ds,'apply_alpha_theme',lambda:None)
    assert ui.sidebar()==(HOME,'Control Tower')
    count=0
    for number,(step,mod) in enumerate(zip(STEPS,modules),1):
        names=[x[0] for x in mod.NAV] if number<=2 else list(mod.NAV)
        state['pmo_active_step']=step
        key='pmo_active_page' if number==1 else f'pmo_active_p{number}_page'
        for name in names:
            calls.clear();state[key]=name
            assert ui.sidebar()==(step,name)
            assert len([kw for _,kw in calls if kw.get('key','').startswith('alpha02_nav_')])==10
            assert any(label==name and kw.get('type')=='primary' for label,kw in calls)
            count+=1
    assert count==53  # inventario de componentes existentes en Beta03
    state['pmo_active_step']='bad route';assert ui.sidebar()==(HOME,'Control Tower')
