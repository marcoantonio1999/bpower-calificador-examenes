import csv
import json
import multiprocessing
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from grader import VERSION, MODEL, GradingError, load_key, validate_key, key_from_solved_pdf, process_folder


class App:
    def __init__(self, root):
        self.root, self.events = root, queue.Queue()
        self.key, self.folder, self.result, self.busy = None, '', None, False
        self.cancel = threading.Event()
        root.title('BPower · Calificador de exámenes')
        root.geometry('850x730')
        root.minsize(670,620)
        root.configure(bg='#f5f7fb')
        style=ttk.Style(); style.theme_use('clam')
        style.configure('TFrame',background='#f5f7fb')
        style.configure('TLabel',background='#f5f7fb',foreground='#1f304b',font=('Segoe UI',10))
        style.configure('TCheckbutton',background='#f5f7fb',font=('Segoe UI',10))
        style.configure('TButton',padding=(12,10),font=('Segoe UI',10))
        style.configure('Primary.TButton',background='#2357a5',foreground='white')
        style.map('Primary.TButton',background=[('active','#174481'),('disabled','#aab7ce')])
        viewport=ttk.Frame(root); viewport.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(viewport,bg='#f5f7fb',highlightthickness=0)
        scrollbar=ttk.Scrollbar(viewport,orient='vertical',command=self.canvas.yview)
        scrollbar.pack(side='right',fill='y'); self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        frame=ttk.Frame(self.canvas,padding=22)
        frame_window=self.canvas.create_window((0,0),window=frame,anchor='nw')
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(frame_window,width=event.width))
        frame.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        root.bind_all('<MouseWheel>',lambda event:self.canvas.yview_scroll(-int(event.delta/120),'units') if event.widget.winfo_toplevel()==root else None)
        ttk.Label(frame,text='BPOWER  /  RECURSOS HUMANOS',font=('Segoe UI',10,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Calificador de exámenes',font=('Segoe UI',22,'bold')).pack(anchor='w',pady=(6,5))
        ttk.Label(frame,text='PDF por carpeta · Opción múltiple con clave · Abiertas con Luna (bajo)').pack(anchor='w')
        step=ttk.Frame(frame); step.pack(fill='x',pady=(18,6))
        step.columnconfigure(0,weight=1);step.columnconfigure(1,weight=1)
        ttk.Button(step,text='1. Cargar respuestas JSON / CSV',command=self.select_key).grid(row=0,column=0,sticky='ew',padx=(0,6))
        ttk.Button(step,text='Clave desde PDF resuelto',command=self.from_pdf).grid(row=0,column=1,sticky='ew',padx=(6,0))
        ttk.Button(step,text='Crear / editar clave de respuestas',command=self.editor).grid(row=1,column=0,columnspan=2,sticky='ew',pady=(6,0))
        self.key_label=ttk.Label(frame,text='Sin clave de respuestas. No se inventan respuestas correctas.',wraplength=780)
        self.key_label.pack(anchor='w',fill='x')
        ttk.Button(frame,text='2. Seleccionar carpeta de exámenes PDF',command=self.select_folder).pack(fill='x',pady=(14,5))
        self.folder_label=ttk.Label(frame,text='No has seleccionado una carpeta.',wraplength=780)
        self.folder_label.pack(anchor='w',fill='x')
        ttk.Separator(frame).pack(fill='x',pady=15)
        ttk.Label(frame,text='API key de Vero · sólo para preguntas abiertas',font=('Segoe UI',10,'bold')).pack(anchor='w')
        self.api_key=tk.StringVar()
        self.key_entry=ttk.Entry(frame,textvariable=self.api_key,show='●',font=('Segoe UI',11))
        self.key_entry.pack(fill='x',ipady=8,pady=(7,5))
        ttk.Label(frame,text='No se guarda en archivos. No se usa ninguna clave de este equipo.',font=('Segoe UI',9)).pack(anchor='w')
        self.consent=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text='Autorizo calificar las abiertas con OpenAI (envío de texto con costo).',variable=self.consent).pack(anchor='w',pady=8)
        ttk.Label(frame,text=f'Modelo: {MODEL} · razonamiento: low · sin subir PDF, imágenes ni campos de contacto.',wraplength=780,font=('Segoe UI',9)).pack(anchor='w')
        controls=ttk.Frame(frame); controls.pack(fill='x',pady=(16,8))
        self.start=ttk.Button(controls,text='3. Calificar y generar Excel',style='Primary.TButton',command=self.run)
        self.start.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.stop=ttk.Button(controls,text='Pausar',state='disabled',command=self.cancel.set); self.stop.pack(side='right')
        self.bar=ttk.Progressbar(frame); self.bar.pack(fill='x')
        self.status=ttk.Label(frame,text='Listo para comenzar.',wraplength=780,justify='left'); self.status.pack(fill='x',pady=10)
        buttons=ttk.Frame(frame); buttons.pack(fill='x')
        self.open_excel=ttk.Button(buttons,text='Abrir Excel',command=lambda:self.open_result('excel'),state='disabled'); self.open_excel.pack(side='left',padx=(0,8))
        self.open_folder=ttk.Button(buttons,text='Ver resultados',command=lambda:self.open_result('output'),state='disabled'); self.open_folder.pack(side='left')
        ttk.Label(frame,text='Las notas de IA requieren validación humana. Un PDF ilegible se marca para revisión; no recibe un cero inventado.',wraplength=780,font=('Segoe UI',9)).pack(anchor='w',pady=12)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.bind('<Configure>',self.resize)
        root.after(150,self.poll)

    def resize(self,event):
        if event.widget==self.root:
            for label in (self.status,self.key_label,self.folder_label): label.configure(wraplength=max(500,event.width-60))
            def wrap_children(widget):
                for child in widget.winfo_children():
                    if isinstance(child,ttk.Label): child.configure(wraplength=max(480,event.width-72))
                    wrap_children(child)
            wrap_children(self.canvas)

    def ensure_idle(self):
        if self.busy:
            messagebox.showinfo('Procesando','Espera a que termine el lote o pulsa Pausar.',parent=self.root)
            return False
        return True

    def set_key(self,key):
        self.key=key
        opened=sum(q['type']=='open' for q in key['questions'])
        self.key_label.configure(text=f'{key["title"]}: {len(key["questions"])} preguntas ({opened} abiertas). Puntos: {sum(q["points"] for q in key["questions"]):g}')

    def select_key(self):
        if not self.ensure_idle(): return
        path=filedialog.askopenfilename(parent=self.root,title='Respuestas correctas / rúbrica',filetypes=[('Clave de respuestas','*.json *.csv')])
        if path:
            try: self.set_key(load_key(path))
            except Exception as error: messagebox.showerror('Clave inválida',str(error) if isinstance(error,GradingError) else 'No se pudo leer la clave.',parent=self.root)

    def from_pdf(self):
        if not self.ensure_idle(): return
        path=filedialog.askopenfilename(parent=self.root,title='Selecciona TU PDF completamente resuelto (clave), no el de un candidato',filetypes=[('PDF','*.pdf')])
        if path:
            self.status.configure(text='Leyendo PDF de respuestas...')
            self.root.update_idletasks()
            try: self.set_key(key_from_solved_pdf(path)); self.status.configure(text='Clave cargada desde el PDF de referencia.')
            except Exception as error: messagebox.showerror('No se pudo cargar',str(error) if isinstance(error,GradingError) else 'No se pudo leer el PDF.',parent=self.root)

    def select_folder(self):
        if not self.ensure_idle(): return
        folder=filedialog.askdirectory(parent=self.root,title='Carpeta que contiene sólo los exámenes de candidatos',mustexist=True)
        if folder: self.folder=folder; self.folder_label.configure(text=folder)

    def editor(self):
        if not self.ensure_idle(): return
        win=tk.Toplevel(self.root); win.title('Clave de respuestas · una fila por pregunta'); win.geometry('1000x650'); win.minsize(700,500)
        top=ttk.Frame(win,padding=12); top.pack(fill='x')
        ttk.Label(top,text='Nombre del examen:').pack(side='left')
        title=tk.StringVar(value=self.key['title'] if self.key else 'Evaluación')
        ttk.Entry(top,textvariable=title,width=55).pack(side='left',padx=10)
        ttk.Label(win,text='Tipo: choice = opción múltiple; open = abierta. Para abiertas: escribe pregunta, respuesta esperada y criterio.').pack(anchor='w',padx=12,pady=5)
        container=ttk.Frame(win); container.pack(fill='both',expand=True,padx=12)
        canvas=tk.Canvas(container,bg='#f5f7fb',highlightthickness=0)
        vertical=ttk.Scrollbar(container,orient='vertical',command=canvas.yview); vertical.pack(side='right',fill='y')
        horizontal=ttk.Scrollbar(win,orient='horizontal',command=canvas.xview); horizontal.pack(fill='x',padx=12)
        canvas.pack(side='left',fill='both',expand=True); canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        grid=ttk.Frame(canvas); canvas.create_window((0,0),window=grid,anchor='nw')
        grid.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        headers=[('id',6),('type',9),('expected',28),('points',7),('prompt',35),('rubric',35),('field',18)]
        labels=['Pregunta','Tipo','Respuesta esperada','Puntos','Enunciado (abiertas)','Criterio / rúbrica','Campo PDF']
        for col,label in enumerate(labels): ttk.Label(grid,text=label,font=('Segoe UI',9,'bold')).grid(row=0,column=col,padx=4,pady=6,sticky='w')
        rows=[]
        def add(q=None):
            q=q or dict(id=str(len(rows)+1),type='choice',expected='',points=1,prompt='',rubric='',field=f'pregunta_{len(rows)+1:02}')
            variables={}
            for col,(key,width) in enumerate(headers):
                var=tk.StringVar(value=str(q.get(key,''))); variables[key]=var
                widget=ttk.Combobox(grid,textvariable=var,values=['choice','open'],state='readonly',width=width) if key=='type' else ttk.Entry(grid,textvariable=var,width=width)
                widget.grid(row=len(rows)+1,column=col,padx=4,pady=3,ipady=5)
            rows.append(variables)
        for q in (self.key['questions'] if self.key else [None]): add(q)
        bottom=ttk.Frame(win,padding=12); bottom.pack(fill='x')
        ttk.Button(bottom,text='Agregar pregunta',command=add).pack(side='left')
        def save():
            try: key=validate_key({'title':title.get(),'questions':[{k:v.get() for k,v in row.items()} for row in rows]})
            except GradingError as error: messagebox.showerror('Revisa la clave',str(error),parent=win); return
            path=filedialog.asksaveasfilename(parent=win,title='Guardar clave privada (no compartir con candidatos)',defaultextension='.json',filetypes=[('JSON','*.json')])
            if path:
                try: Path(path).write_text(json.dumps(key,ensure_ascii=False,indent=2),encoding='utf-8')
                except OSError: messagebox.showerror('No se guardó','Revisa permisos de la carpeta.',parent=win); return
                self.set_key(key); win.destroy()
        ttk.Button(bottom,text='Guardar y usar clave',style='Primary.TButton',command=save).pack(side='right')

    def run(self):
        if not self.ensure_idle(): return
        if not self.key or not self.folder:
            messagebox.showerror('Faltan datos','Carga una clave de respuestas y selecciona la carpeta de exámenes.',parent=self.root); return
        has_open=any(q['type']=='open' for q in self.key['questions'])
        api_key=self.api_key.get().strip()
        if has_open and (not self.consent.get() or not api_key):
            messagebox.showerror('Preguntas abiertas','Introduce tu API key y autoriza el envío de texto para calificar preguntas abiertas.',parent=self.root); return
        self.busy=True; self.cancel.clear(); self.start.configure(state='disabled'); self.stop.configure(state='normal')
        self.open_excel.configure(state='disabled'); self.open_folder.configure(state='disabled')
        self.key_entry.configure(state='disabled'); self.status.configure(text='Procesando...')
        folder,key,consent=self.folder,self.key,self.consent.get()
        def worker():
            try:
                result=process_folder(folder,key,api_key=api_key,ai_enabled=bool(has_open and consent),progress=lambda i,n:self.events.put(('progress',(i,n))),cancelled=self.cancel.is_set)
                self.events.put(('done',result))
            except Exception as error:
                self.events.put(('error',str(error) if isinstance(error,GradingError) else 'No se pudo finalizar. Revisa permisos, espacio y carpeta. Los PDF originales siguen intactos.'))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    i,n=value; self.bar.configure(maximum=n,value=i-1); self.status.configure(text=f'Procesando PDF {i} de {n}...')
                else:
                    self.busy=False; self.start.configure(state='normal'); self.stop.configure(state='disabled'); self.key_entry.configure(state='normal'); self.api_key.set('')
                    if kind=='error': self.status.configure(text=value)
                    else:
                        self.result=value; self.bar.configure(value=value['count'])
                        self.status.configure(text=f'{"Pausado" if self.cancel.is_set() else "Terminado"}: {value["count"]} PDF procesados · {value["review"]} para revisar.\nResultado guardado en una carpeta nueva junto a los PDF.')
                        self.open_excel.configure(state='normal'); self.open_folder.configure(state='normal')
        except queue.Empty: pass
        self.root.after(150,self.poll)

    def open_result(self,key):
        try: os.startfile(self.result[key])
        except OSError: messagebox.showerror('No se pudo abrir','Abre el resultado desde la carpeta de exámenes. Necesitas un lector de Excel compatible.',parent=self.root)

    def close(self):
        if self.busy: messagebox.showinfo('Procesando','Pulsa Pausar y espera a que termine el archivo actual.',parent=self.root)
        else: self.api_key.set(''); self.root.destroy()


if __name__=='__main__':
    multiprocessing.freeze_support()
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        from self_test import run
        run(Path(sys.argv[2]))
    else:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError,OSError): pass
        App(tk.Tk()).root.mainloop()
