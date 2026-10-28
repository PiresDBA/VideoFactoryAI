"""Script para limpar cache de clips e forçar regeneração multi-imagem."""
import os
import shutil
from pathlib import Path

print("=== Limpeza de Cache para Regeneração Multi-Imagem ===")
print()

project_dir = Path(r'C:\Fabrica-de-videos\projetos\makete_ho')
temp_clips_dir = project_dir / 'temp_clips'
temp_clips_backup = project_dir / 'temp_clips_backup_old_single_image'

# Verificar se há clips
if not temp_clips_dir.exists():
    print(f"[INFO] Diretório não existe: {temp_clips_dir}")
    exit(0)

clips = list(temp_clips_dir.glob('clip_*.mp4'))
print(f"[INFO] Encontrados {len(clips)} clips em cache")
print(f"[INFO] Diretório: {temp_clips_dir}")
print()

if not clips:
    print("[OK] Nenhum clip para limpar")
    exit(0)

# Perguntar se quer fazer backup
print("Opções:")
print("  1. Mover clips para backup (recomendado)")
print("  2. Deletar clips permanentemente")
print("  3. Cancelar")
print()

choice = input("Escolha (1/2/3): ").strip()

if choice == '3':
    print("[INFO] Cancelado pelo usuário")
    exit(0)
elif choice == '2':
    # Deletar permanentemente
    print(f"\n[DELETANDO] Removendo {len(clips)} clips...")
    for clip in clips:
        try:
            clip.unlink()
            print(f"  Deletado: {clip.name}")
        except Exception as e:
            print(f"  [ERRO] Falha ao deletar {clip.name}: {e}")
elif choice == '1':
    # Mover para backup
    if temp_clips_backup.exists():
        print(f"[INFO] Backup já existe: {temp_clips_backup}")
        backup_choice = input("Sobrescrever backup? (s/n): ").strip().lower()
        if backup_choice == 's':
            shutil.rmtree(temp_clips_backup)
        else:
            print("[INFO] Mantendo backup existente. Cancelando.")
            exit(0)
    
    print(f"\n[MOVENDO] Criando backup em: {temp_clips_backup}")
    temp_clips_backup.mkdir(parents=True, exist_ok=True)
    
    for clip in clips:
        try:
            dest = temp_clips_backup / clip.name
            shutil.move(str(clip), str(dest))
            print(f"  Movido: {clip.name}")
        except Exception as e:
            print(f"  [ERRO] Falha ao mover {clip.name}: {e}")
else:
    print("[ERRO] Opção inválida")
    exit(1)

print()
print("=" * 60)
print("[OK] Cache limpo com sucesso!")
print()
print("PRÓXIMOS PASSOS:")
print("1. Execute a GUI novamente")
print("2. Selecione múltiplas fotos para cada cena")
print("3. O sistema agora vai processar TODAS as fotos selecionadas")
print("4. Os clips serão regenerados com múltiplas imagens concatenadas")
print()
print("IMPORTANTE: Não use --resume para forçar regeneração completa!")
print("=" * 60)
