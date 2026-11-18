import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='İç Kontrol Risk Ajansı | Demo', page_icon='🛡️', layout='wide')
st.markdown('''<style>.block-container{padding-top:1.5rem;max-width:1450px}div[data-testid="stMetric"]{background:#f3f6fb;padding:15px;border-radius:12px;border:1px solid #e4e9f2}</style>''',unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def generate_data(n=10000, seed=42):
    rng=np.random.default_rng(seed)
    age=rng.integers(18,91,n)
    inactive=rng.integers(0,730,n)
    amount=np.round(rng.lognormal(8.4,1.15,n),2)
    avg=np.round(rng.lognormal(8.1,0.85,n),2)
    new_recipient=rng.random(n)<0.21
    hour=rng.integers(0,24,n)
    daily_count=rng.poisson(2.2,n)+1
    daily_total=np.round(amount*rng.uniform(1,3,n),2)
    times=pd.Timestamp('2026-11-18')-pd.to_timedelta(rng.integers(0,30,n),unit='D')+pd.to_timedelta(hour,unit='h')
    df=pd.DataFrame({'transaction_id':[f'TX-{i:06d}' for i in range(1,n+1)],'customer_id':[f'DEMO-{x:05d}' for x in rng.integers(1,4500,n)],'transaction_datetime':times,'age':age,'inactivity_days':inactive,'transaction_amount':amount,'historical_avg_amount':avg,'new_recipient':new_recipient,'transaction_hour':hour,'daily_transaction_count':daily_count,'daily_transfer_total':daily_total})
    ratio=df.transaction_amount/df.historical_avg_amount.clip(lower=1)
    flags={
      '365+ gün hareketsizlik':df.inactivity_days>=365,
      '65 yaş ve üzeri':df.age>=65,
      'Hareketsizlik + ileri yaş':(df.inactivity_days>=365)&(df.age>=65),
      'Yeni alıcı':df.new_recipient,
      'Gece işlemi (00:00–05:59)':df.transaction_hour<6,
      'Geçmiş ortalamanın 5 katı':ratio>=5,
      'Gün içinde 6+ işlem':df.daily_transaction_count>=6,
      'Yüksek günlük transfer':df.daily_transfer_total>=150000,
    }
    weights={'365+ gün hareketsizlik':20,'65 yaş ve üzeri':10,'Hareketsizlik + ileri yaş':15,'Yeni alıcı':15,'Gece işlemi (00:00–05:59)':10,'Geçmiş ortalamanın 5 katı':15,'Gün içinde 6+ işlem':10,'Yüksek günlük transfer':15}
    df['risk_score']=np.minimum(100,sum(flags[k].astype(int)*v for k,v in weights.items())).astype(int)
    df['risk_level']=np.select([df.risk_score>=60,df.risk_score>=30],['YÜKSEK','ORTA'],default='DÜŞÜK')
    flag_arr=np.column_stack([v.to_numpy() for v in flags.values()])
    names=list(flags)
    df['risk_reasons']=[' | '.join(names[j] for j in np.flatnonzero(row)) or 'Belirgin kural tetiklenmedi' for row in flag_arr]
    df['recommended_actions']=np.select([df.risk_score>=60,df.risk_score>=30],['Öncelikli manuel inceleme; müşteri ve alıcı doğrulaması','İşlem geçmişiyle karşılaştırma ve gerektiğinde doğrulama'],default='Rutin izleme')
    return df

st.title('🛡️ İç Kontrol Risk Ajansı')
st.caption('Herkese açık tanıtım • 10.000 tamamen sentetik işlem • Kural tabanlı, açıklanabilir risk puanlama • Gerçek müşteri verisi yoktur')
st.info('Bu sürüm bir araştırma ve tanıtım prototipidir. Risk skoru, dolandırıcılık veya suç tespiti anlamına gelmez. Yapay zekâ/ML modeli bu sürümde çalıştırılmamaktadır.')
df=generate_data()
with st.sidebar:
    st.header('Filtreler')
    levels=st.multiselect('Risk seviyesi',['YÜKSEK','ORTA','DÜŞÜK'],default=['YÜKSEK','ORTA','DÜŞÜK'])
    min_score=st.slider('Asgari risk puanı',0,100,0,5)
    dormant=st.checkbox('Yalnızca 365+ gün hareketsiz')
    older=st.checkbox('Yalnızca 65 yaş ve üzeri')
    st.divider()
    st.caption('Örnek veri sabit tohumla üretilir; tüm ziyaretçiler aynı demo veri kümesini görür.')
view=df[df.risk_level.isin(levels)&(df.risk_score>=min_score)]
if dormant:view=view[view.inactivity_days>=365]
if older:view=view[view.age>=65]
a,b,c,d=st.columns(4)
a.metric('Toplam sentetik işlem',f'{len(df):,}')
b.metric('Filtrelenen işlem',f'{len(view):,}')
c.metric('Yüksek riskli işlem',f'{(view.risk_level=="YÜKSEK").sum():,}')
d.metric('Ortalama risk skoru',f'{view.risk_score.mean():.1f}/100' if len(view) else '—')
t1,t2,t3=st.tabs(['📊 Risk panosu','📋 İşlem listesi','🔎 Vaka inceleme'])
with t1:
    left,right=st.columns(2)
    with left:
        st.subheader('Risk seviyelerine göre dağılım')
        counts=view.risk_level.value_counts().reindex(['YÜKSEK','ORTA','DÜŞÜK'],fill_value=0)
        st.bar_chart(counts)
    with right:
        st.subheader('Risk puanı dağılımı')
        st.bar_chart(view.groupby(pd.cut(view.risk_score,bins=[-1,19,39,59,79,100],labels=['0–19','20–39','40–59','60–79','80–100']),observed=False).size())
    st.subheader('Günlük işlem eğilimi')
    if len(view):
        trend=view.assign(gün=view.transaction_datetime.dt.date).groupby('gün').agg(İşlem=('transaction_id','count'),Yüksek_Risk=('risk_level',lambda x:(x=='YÜKSEK').sum()))
        st.line_chart(trend)
with t2:
    st.subheader('İşlem listesi')
    cols=['transaction_id','customer_id','transaction_datetime','age','inactivity_days','transaction_amount','new_recipient','risk_score','risk_level']
    st.dataframe(view[cols].sort_values('risk_score',ascending=False),use_container_width=True,hide_index=True,height=440)
    st.download_button('Filtrelenen sentetik verileri CSV indir',view.to_csv(index=False).encode('utf-8-sig'),'ic_kontrol_demo_islemler.csv','text/csv')
with t3:
    st.subheader('İşlem bazında açıklanabilir risk değerlendirmesi')
    if view.empty:st.warning('Seçilen filtrelerde işlem bulunamadı.')
    else:
        ids=view.sort_values(['risk_score','transaction_amount'],ascending=False).transaction_id.tolist()
        selected=st.selectbox('İşlem seçin',ids)
        row=view.loc[view.transaction_id==selected].iloc[0]
        a,b,c,d=st.columns(4)
        a.metric('Risk seviyesi',row.risk_level);b.metric('Risk puanı',f'{row.risk_score}/100');c.metric('Hareketsizlik',f'{row.inactivity_days} gün');d.metric('Tutar',f'{row.transaction_amount:,.2f} TL')
        st.markdown('**Risk gerekçeleri**')
        for reason in row.risk_reasons.split(' | '):st.write('• '+reason)
        st.markdown('**Önerilen kontrol**')
        st.write(row.recommended_actions)
        st.caption('Bu demo vaka bilgisi kaydetmez; kullanıcı hesabı veya gerçek müşteri kaydı içermez.')
st.divider()
st.caption('İç Kontrol Risk Ajansı — tanıtım amaçlı kural tabanlı prototip. Risk ağırlıkları örnektir, bankacılık kararı veya hukuki değerlendirme yerine geçmez.')
