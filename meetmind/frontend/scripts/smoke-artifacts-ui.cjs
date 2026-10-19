// Real built UI; API/model responses mocked. No servers or external messages.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
  const root=path.resolve(__dirname,'..');
  const html=fs.readFileSync(path.join(root,'dist/index.html'),'utf8');
  const commitment={id:'commit-1',revision:1,task:'Send the report',owner:'Sara',deadline:'Friday',
    kind:'commitment',review_status:'approved',status:'approved',needs_review:false,source_id:1,
    evidence:[{quote:'I will send the report by Friday.',source_ids:[1]}]};
  const meeting={id:'meeting-1',title:'Artifact UI fixture',status:'extracted',model:'fixture',actions:[commitment],
    segments:[{id:1,speaker:'Sara',text:'I will send the report by Friday.',source:'I will send the report by Friday.'}]};
  let draft=null,create;
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('http://127.0.0.1:5199/**',async route=>{
      const req=route.request(),name=new URL(req.url()).pathname;
      if(name.startsWith('/api/')){
        let data;
        if(name==='/api/health')data={ollama:'offline',bert:{status:'not loaded'}};
        else if(name==='/api/meetings')data=[meeting];
        else if(name==='/api/meetings/meeting-1')data=meeting;
        else if(name==='/api/meetings/meeting-1/artifacts'){
          create=req.postDataJSON();
          draft={id:'draft-1',meeting_id:meeting.id,meeting_title:meeting.title,status:'draft',revision:1,
            to:create.to,subject:'Report follow-up',body:'Please send the report by Friday.',model:'fixture',
            approval_valid:false,source_current:true,source:commitment,policy:{can_approve:true,violations:[]},history:[]};
          data=draft;
        }else if(name==='/api/artifacts')data=draft ? [draft]:[];
        else if(name.endsWith('/review')){
          const body=req.postDataJSON();
          assert.equal(body.revision,draft.revision);
          draft={...draft,status:body.decision,approval_valid:body.decision==='approved',revision:draft.revision+1};data=draft;
        }else if(name==='/api/artifacts/draft-1' && req.method()==='PATCH'){
          const body=req.postDataJSON();assert.equal(body.revision,draft.revision);
          draft={...draft,...body,status:'draft',approval_valid:false,revision:draft.revision+1};data=draft;
        }else if(name==='/api/artifacts/draft-1')data=draft;
        else return route.fulfill({status:404,json:{detail:'Unexpected API request'}});
        return route.fulfill({json:data});
      }
      if(name==='/')return route.fulfill({body:html,contentType:'text/html'});
      if(name.startsWith('/assets/'))return route.fulfill({body:fs.readFileSync(path.join(root,'dist',name)),
        contentType:name.endsWith('.css')?'text/css':'text/javascript'});
      return route.fulfill({status:404});
    });
    await page.goto('http://127.0.0.1:5199/');
    await page.getByRole('button',{name:/Artifact UI fixture/}).click();
    await page.getByRole('button',{name:'Draft follow-up',exact:true}).click();
    await page.getByLabel('Recipient email addresses').fill('sara@example.com');
    await page.getByRole('button',{name:'Generate email draft',exact:true}).click();
    await page.getByLabel('Subject',{exact:true}).waitFor();
    assert.equal(create.commitment_revision,1);assert.equal(create.commitment_id,'commit-1');
    assert.ok(create.idempotency_key);
    await page.getByRole('button',{name:'Approve draft',exact:true}).click();
    await page.getByText('This exact draft is approved. It has not been sent.',{exact:true}).waitFor();
    await page.getByLabel('Message',{exact:true}).fill('Please send the updated report by Friday.');
    assert.equal(await page.getByRole('button',{name:'Approve draft',exact:true}).isDisabled(),true);
    await page.getByRole('button',{name:'Save draft changes',exact:true}).click();
    await page.getByRole('button',{name:'Approve draft',exact:true}).waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('button.primary:disabled'));
    assert.equal(draft.approval_valid,false);
    await page.getByRole('button',{name:'Reject draft',exact:true}).click();
    await page.getByRole('button',{name:'Reload draft',exact:true}).click();
    assert.equal(draft.status,'rejected');
    fs.mkdirSync(path.join(root,'runs'),{recursive:true});
    await page.screenshot({path:path.join(root,'runs/artifacts-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:path.join(root,'runs/artifacts-mobile.png'),fullPage:true});
    await page.reload();
    await page.getByRole('button',{name:'Follow-up drafts',exact:true}).click();
    await page.getByRole('button',{name:/Report follow-up/}).click();
    assert.equal(await page.getByLabel('Message',{exact:true}).inputValue(),'Please send the updated report by Friday.');
    assert.deepEqual(errors,[]);
    console.log('Artifact UI passed: approved source, explicit recipients, draft, approval, edit invalidation, rejection, reload and mobile. API mocked.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
