# ComfyUI Premium Track (optionnel)

## But
Ajouter génération visuelle premium (b-roll, backgrounds stylisés, assets IA).

## Bootstrap
```bash
./scripts/bootstrap_comfyui.sh
```

## Wrappers proposés
- `scripts/comfy_generate_bg.sh` (à créer ensuite): lance un workflow JSON prédéfini
- Entrées: prompt, seed, ratio 9:16
- Sorties: PNG/JPG pour montage short-form

## Pré-requis comptes/fichiers
- Checkpoints SDXL / Flux (licences à valider)
- Eventuel accès GPU distant (RunPod/Vast/Modal)

## Note
Ce repo prépare le bootstrap + doc. La prod image premium dépend des modèles et ressources GPU.
