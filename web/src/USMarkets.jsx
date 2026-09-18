import React,{useEffect,useState} from 'react';
import USResearch from './USResearch';
import USPaper from './USPaper';
import USModels from './USModels';
import USWeatherStudy from './USWeatherStudy';
import USBenterStudy from './USBenterStudy';
import USBasketStudy from './USBasketStudy';
import USPortfolioStudy from './USPortfolioStudy';
import USAllocationStudy from './USAllocationStudy';
export default function USMarkets(){
 const [state,setState]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;const refresh=()=>fetch('/api/us').then(r=>{if(!r.ok)throw Error('US feed unavailable');return r.json()}).then(s=>{if(active)setState(s)}).catch(e=>{if(active)setError(e.message)});refresh();const timer=setInterval(refresh,10000);return()=>{active=false;clearInterval(timer)}},[]);
 return <><USPaper/><USAllocationStudy/><USPortfolioStudy/><USBasketStudy/><USBenterStudy/><USWeatherStudy/><USResearch/><USModels/><section className="panel detail-panel"><h2>Polymarket US</h2><p>US venue only. Public market data uses the official US gateway. No VPN, international exchange connection, or live orders.</p><p className="notice">International backtests and paper accounts are archived. US strategy adaptation and validation are in progress; those earlier returns are not US results.</p>{error&&<p role="alert">{error}</p>}<p>{state?.running?'US collector running':'US collector stopped'} · {state?.market_count??0} active markets in the latest bounded batch · {state?.books?.length??0} sampled order books</p><p>Discovery: {state?.discovery_complete?'completed this bounded scan':'partial / collecting'} · {Object.entries(state?.categories||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p>{state?.error&&<p className="notice">{state.error}</p>}<p>Paper trading and backtesting will use US contract rules, verified contract quantities, and the US fee schedule. US screening results are shown above; the separate US forward experiment is collecting new evidence.</p><div className="table-scroll"><table><thead><tr><th>US market</th><th>Category</th><th>Contract</th></tr></thead><tbody>{(state?.markets||[]).slice(0,100).map(m=><tr key={m.id}><td>{m.question}</td><td>{m.category||'Unclassified'}</td><td>{m.slug}</td></tr>)}</tbody></table></div><p className="muted">Showing the first 100 contracts in this batch. Discovery advances across batches; coverage is partial. A public-data connection does not verify individual account eligibility.</p></section></>
}
