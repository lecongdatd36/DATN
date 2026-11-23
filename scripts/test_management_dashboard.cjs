const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {runInNewContext}=require('node:vm');

test('daily revenue chart renders negative refund days inside its plotting area',()=>{
  class Element {
    constructor(tag){this.tag=tag;this.attrs={};this.children=[];}
    setAttribute(key,value){this.attrs[key]=value;}
    append(...items){this.children.push(...items);}
  }
  const svg=new Element('svg'),table=new Element('div');
  const data={labels:['01/11','02/11','03/11'],revenue:[100000,-50000,0],orders:[1,0,0],show_orders:false};
  const document={
    querySelector(selector){return {'#dashboard-chart-data':{textContent:JSON.stringify(data)},'[data-dashboard-chart]':svg,
      '[data-chart-table]':table,'#dashboard-order-data':{textContent:'[]'}}[selector]||null;},
    createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)
  };
  runInNewContext(readFileSync(join(__dirname,'../static/js/management-dashboard.js'),'utf8'),{document});
  const bars=svg.children.filter(node=>node.tag==='rect');
  assert.equal(bars.length,3);
  for(const bar of bars){assert.ok(bar.attrs.height>0);assert.ok(bar.attrs.y>=20);assert.ok(bar.attrs.y+bar.attrs.height<=176);}
  assert.match(bars[1].attrs.fill,/danger/);
  assert.match(bars[1].children[0].textContent,/-50/);
  assert.equal(table.children[0].children.length,4);
});
