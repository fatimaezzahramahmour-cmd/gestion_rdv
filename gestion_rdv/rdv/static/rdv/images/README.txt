Photos du site (fichiers locaux, toujours affichées) :
- patient-dentaire-1.jpg
- cabinet-dentaire-2.jpg
- soins-dentaire-3.jpg

Si ces fichiers manquent, depuis ce dossier exécutez (PowerShell) :
  Invoke-WebRequest -Uri "https://images.unsplash.com/photo-1606811841689-23dfddce3e95?w=1400&q=85&fm=jpg" -OutFile "patient-dentaire-1.jpg" -UseBasicParsing
  Invoke-WebRequest -Uri "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=1400&q=85&fm=jpg" -OutFile "cabinet-dentaire-2.jpg" -UseBasicParsing
  Invoke-WebRequest -Uri "https://images.unsplash.com/photo-1629909613654-28e377c37b09?w=1400&q=85&fm=jpg" -OutFile "soins-dentaire-3.jpg" -UseBasicParsing
