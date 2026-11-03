const taskList = document.querySelector('#tasks');
const input = document.querySelector('#title-input');
const form = document.querySelector('#add-form');
document.querySelector('#today').textContent = new Date().toLocaleDateString('en-US', {weekday:'short',month:'short',day:'numeric'});

async function api(path, options={}) {
  const response = await fetch('/api'+path, {headers:{'Content-Type':'application/json'},...options});
  const result = await response.json();
  if(!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function element(tag, cls, content='') {
  const el = document.createElement(tag);
  if(cls) el.className = cls;
  el.textContent=content;
  return el;
}
async function render() {
  try {
    const tasks = await api('/tasks');
    document.querySelector('#total').textContent=tasks.length;
    document.querySelector('#completed').textContent=tasks.filter(t=>t.done).length;
    document.querySelector('#remaining').textContent=tasks.filter(t=>!t.done).length;
    document.querySelector('#count-badge').textContent=`${tasks.length} task${tasks.length===1?'':'s'}`;
    taskList.replaceChildren();
    if(!tasks.length) {taskList.append(element('div','empty','Nothing here yet. Add your first task!'));return;}
    for(const task of tasks) {
      const row=element('div','task-row'+(task.done?' done':''));
      const check=element('button','checkbox'+(task.done?' checked':''),task.done?'✓':'');
      check.type='button'; check.setAttribute('aria-label','Toggle '+task.title);
      check.onclick=async()=>{await api('/tasks/'+task.id,{method:'PATCH',body:JSON.stringify({done:!task.done})});await render();};
      const title=element('span','task-title',task.title);
      const remove=element('button','delete','×');remove.title='Delete task';remove.setAttribute('aria-label','Delete '+task.title);
      remove.onclick=async()=>{await api('/tasks/'+task.id,{method:'DELETE'});await render();};
      row.append(check,title,remove);taskList.append(row);
    }
  } catch(err) {taskList.replaceChildren(element('div','empty','Error: '+err.message));}
}
form.addEventListener('submit',async e=>{e.preventDefault();try{await api('/tasks',{method:'POST',body:JSON.stringify({title:input.value})});input.value='';await render();}catch(err){alert(err.message);}});
render();
