import subprocess,time,uno,sys,os
from com.sun.star.beans import PropertyValue
def P(n,v):
    p=PropertyValue(); p.Name=n; p.Value=v; return p
proc=subprocess.Popen(['soffice','--headless','--invisible','--norestore','--accept=socket,host=localhost,port=2002;urp;'])
ctx=None
for i in range(40):
    try:
        lc=uno.getComponentContext(); r=lc.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',lc)
        ctx=r.resolve('uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext'); break
    except Exception: time.sleep(0.5)
desk=ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',ctx)
src=uno.systemPathToFileUrl(os.path.abspath(sys.argv[1]))
doc=desk.loadComponentFromURL(src,'_blank',0,(P('Hidden',True),))
idx=doc.getDocumentIndexes()
for i in range(idx.getCount()): idx.getByIndex(i).update()
doc.refresh()
for i in range(idx.getCount()): idx.getByIndex(i).update()
doc.storeToURL(uno.systemPathToFileUrl(os.path.abspath(sys.argv[2])),(P('FilterName','writer_pdf_Export'),))
doc.storeToURL(uno.systemPathToFileUrl(os.path.abspath(sys.argv[3])),(P('FilterName','MS Word 2007 XML'),))
doc.close(True)
try: desk.terminate()
except Exception: pass
proc.wait(timeout=30)
print('indexes',idx.getCount())
