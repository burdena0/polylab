import React from 'react';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,CartesianGrid,Tooltip,Legend,ReferenceLine} from 'recharts';
export const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n??0);
export const date=t=>new Date(t*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'});
export default function Chart({series,capital=50,drawdown=false}){
 const length=Math.max(0,...series.map(s=>s.data?.length||0));
 const data=Array.from({length},(_,i)=>{const row={t:series[0]?.data[i]?.t};series.forEach(s=>row[s.name]=s.data[i]?.[drawdown?'drawdown':'equity']);return row});
 if(!length)return <div className="empty">No recorded curve yet. Run a backtest to generate results.</div>;
 return <div className="chart" role="img" aria-label={drawdown?'Drawdown over the evaluation period':'Simulated equity over the evaluation period'}><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{top:18,right:16,bottom:10,left:0}}><CartesianGrid stroke="#e9edf2" vertical={false}/><XAxis dataKey="t" tickFormatter={date} minTickGap={65} tick={{fontSize:12,fill:'#687a91'}} axisLine={false} tickLine={false}/><YAxis tickFormatter={money} domain={drawdown?[0,'auto']:['auto','auto']} width={65} tick={{fontSize:12,fill:'#687a91'}} axisLine={false} tickLine={false}/><Tooltip labelFormatter={date} formatter={money} contentStyle={{borderRadius:8,borderColor:'#dce4ed',fontSize:13}}/>{!drawdown&&<ReferenceLine y={capital} stroke="#a4b0c0" strokeDasharray="4 4"/>}<Legend iconType="circle" iconSize={8} wrapperStyle={{fontSize:12,paddingTop:16}}/>{series.map(s=><Line key={s.name} name={s.name} dataKey={s.name} stroke={s.color} strokeWidth={2.2} dot={false} type="stepAfter" isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div>
}
