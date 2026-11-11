(() => {
    'use strict';
    const source=document.querySelector('#dashboard-chart-data');
    if(!source)return;
    const data=JSON.parse(source.textContent),svg=document.querySelector('[data-dashboard-chart]');
    const node=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;};
    const revenueMax=Math.max(1000000,...data.revenue),orderMax=Math.max(1,...data.orders);
    const width=620,height=155,left=48,top=20,step=width/data.labels.length;
    for(let i=0;i<=4;i++){
        const y=top+height-height*i/4;
        svg.append(node('line',{x1:left,y1:y,x2:left+width,y2:y,stroke:'var(--cqd-chart-grid,#e0e8f2)','stroke-width':.7}));
        svg.append(node('text',{x:left-8,y:y+3,'text-anchor':'end',fill:'var(--cqd-chart-axis,#7b90aa)','font-size':9},(revenueMax*i/4/1e6).toLocaleString('vi-VN',{maximumFractionDigits:1})));
        if(data.show_orders)svg.append(node('text',{x:left+width+9,y:y+3,fill:'var(--cqd-chart-orders,#1498ac)','font-size':9},(orderMax*i/4).toLocaleString('vi-VN',{maximumFractionDigits:1})));
    }
    const points=[];
    data.labels.forEach((label,i)=>{
        const x=left+step*(i+.5),h=data.revenue[i]/revenueMax*height;
        const bar=node('rect',{x:x-step*.21,y:top+height-h,width:Math.max(2,step*.42),height:Math.max(h,.8),rx:3,fill:'var(--cqd-chart-revenue,#2563eb)'});
        bar.append(node('title',{},`${label}: ${data.revenue[i].toLocaleString('vi-VN')}đ · ${data.orders[i]} đơn`));svg.append(bar);
        const y=top+height-data.orders[i]/orderMax*height;points.push([x,y]);
        if(data.labels.length<=14||i%5===0||i===data.labels.length-1)svg.append(node('text',{x,y:top+height+22,'text-anchor':'middle',fill:'var(--cqd-chart-axis,#7b90aa)','font-size':9},label));
    });
    if(data.show_orders){svg.append(node('polyline',{points:points.map(p=>p.join(',')).join(' '),fill:'none',stroke:'var(--cqd-chart-orders,#1498ac)','stroke-width':2}));points.forEach(([x,y],i)=>{const point=node('circle',{cx:x,cy:y,r:3,fill:'var(--cqd-chart-orders,#1498ac)'});point.append(node('title',{},`${data.labels[i]}: ${data.orders[i]} đơn`));svg.append(point);});}
    const table=document.createElement('table'),head=document.createElement('tr');
    ['Ngày','Doanh thu (đ)',...(data.show_orders?['Số đơn']:[])].forEach(t=>{const th=document.createElement('th');th.textContent=t;head.append(th);});table.append(head);
    data.labels.forEach((day,i)=>{const row=document.createElement('tr');[day,data.revenue[i].toLocaleString('vi-VN'),...(data.show_orders?[data.orders[i]]:[])].forEach(value=>{const td=document.createElement('td');td.textContent=value;row.append(td);});table.append(row);});document.querySelector('[data-chart-table]').append(table);
    const distribution=JSON.parse(document.querySelector('#dashboard-order-data').textContent),total=distribution.reduce((sum,item)=>sum+item.count,0);
    const donut=document.querySelector('[data-order-donut]'),legend=document.querySelector('[data-order-legend]');
    if(!donut)return;
    const colors=['#60a5fa','#2563eb','#22a6b8','#55a784','#de8c8c'];let offset=0;
    const slices=[];
    distribution.forEach((item,i)=>{
        if(!item.count)return;
        const end=offset+item.count/total*100;slices.push(`${colors[i]} ${offset}% ${end}%`);offset=end;
        const li=document.createElement('li'),dot=document.createElement('i'),label=document.createElement('span'),count=document.createElement('strong');dot.style.setProperty('--dot-color',colors[i]);label.textContent=item.label;count.textContent=item.count;li.append(dot,label,count);legend.append(li);
    });
    if(total)donut.style.background=`conic-gradient(${slices.join(',')})`;
    else {const empty=document.createElement('li');empty.textContent='Chưa có đơn hôm nay';legend.append(empty);}
})();
