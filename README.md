Minden nap végén a legfrissebb CSV fájlok és képek automatiusan exportálásra kerülnek befoglalva térképről ([link](https://www.google.com/maps/d/viewer?mid=1hjOcx3VIAH9MZLk4EHSbGdCHQHe35R0), [link](https://offos.ch/befoglalva)) és feltöltésre kerülnek erre a repora. A commit neve tartalmazza, hogy melyik időpontról valók a fájlok.

A mappák neve a "Képek" mappában az adott layerhez tartoznak a Google mymaps-en. Egy adott kép neve pedig a koordináta ahol a kép készült (avagy ahova matrica ragasztva lett), majd utána szövegesen hogy hányadik kép, ha több kép készült ugyanarról a matricáról, amely megmondja, hogy a CSV fájlban az adott ponthoz hányadik dátumhoz tartozik a kép.

Példa:

Van 2 db kép egy koordinátához:
  - 46.144588,18.150432 (1.).png
  - 46.144588,18.150432 (2.).png

A CSV fájlban a két koordináta fel van cserélve ahhoz képest ahogyan a térkép mutatja meg ahogy a googleben rá lehet keresni, plusz a CSV fájlban tárolt koordináta az néha "pontosabb", mint a kép nevében lévő koordináta, ezért érdemes a kép nevében lévő egyik koordináta alapján keresni a CSV fájlban.
CSV fájlban így néz ki egy pont:

&emsp;"POINT (18.150432 46.144588)",Orfű,Buci:\
&emsp;2023. 09. 18.?\
&emsp;Petaki:\
&emsp;2024. 06. 28.

Ehhez a koordinátához két dátum tartozik, így kettő kép is. Az első dátumhoz az "46.144588,18.150432 (1.).png" nevű kép, a második dátumhoz pedig a "46.144588,18.150432 (2.).png" nevű kép tartozik.

A repo tartalmaz két kmz fájlt is,  a térképen matricákat tároló layerenként egyet. Egy kmz file egy referenciát tartalmaz az aktuális mymaps tartalomra amely alapján frissül a backup.
