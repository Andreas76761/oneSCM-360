"""Small, read-only register counts. Tool views count their available inputs."""
import json

def counts(store):
 with store.connect() as db:
  db.execute("BEGIN")
  def count(table):return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
  outlines=[json.loads(r[0]) for r in db.execute('SELECT payload FROM outlines')]
  sources=count('sources');chunks=count('chunks');images=count('media');internal=count('internal_entries');library=count('library');n=len(outlines)
  values={
   'appendices-button':(count('appendix_entries'),'Anhangseinträge, alle Sprachen zusammen'),
   'dashboard-button':(sources+images,'Quellen und Bilder'),
   'overview-button':(n,'Gespeicherte Gliederungen'),
   'compare-button':(n,'Zum Vergleich verfügbare Gliederungen'),
   'backup-button':(None,'Externe Sicherungsdateien werden nicht zentral gezählt'),
   'variants-button':(n,'Für Varianten verfügbare Gliederungen'),
   'design-button':(count('design_patterns')+count('layouts'),'Gespeicherte Patterns und Office-Vorlagen; eingebaute Startvorlagen nicht mitgezählt'),
   'ai-exchange-button':(count('ai_exchanges'),'Gespeicherte KI-Aufträge'),
   'rag-button':(chunks+images+internal+library+n,'Basisobjekte: Chunks, Bilder, interne Einträge, Bibliotheksbausteine und Gliederungen; keine Trefferzahl'),
   'image-activation-button':(sum(len(c.get('media',[])) for o in outlines for c in o['chapters']),'Bild- und Klickstreckenzuordnungen'),
   'content-flags-button':(sources+images+internal,'Analysierbare Quellen, Screens und interne Notizen'),
   'sources-button':(sources,'Quellen; '+str(chunks)+' Text-Chunks'),
   'markdown-tool':(sum(1 for (name,) in db.execute('SELECT name FROM sources') if name.lower().endswith(('.md','.markdown'))),'Importierte Markdown-Quellen; Konverter-Dateiauswahl erfolgt separat'),
   'agents-button':(count('hub_jobs'),'Gespeicherte Orchestrator-Aufträge'),
   'jobs-button':(count('agent_jobs'),'Gespeicherte bisherige Agentenläufe'),
   'internal-button':(internal,'Interne Einträge einschließlich FAQ'),
   'chat-button':(count('internal_chats'),'Gespeicherte Chats'),
   'releases-button':(count('release_packages'),'Releasepakete'),
   'conflicts-button':(count('knowledge_reviews'),'Gespeicherte Quellenprüfungen')}
 return {key:{'count':value,'description':description} for key,(value,description) in values.items()}
