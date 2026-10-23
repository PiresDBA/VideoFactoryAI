"""
VideoFactoryAI: Sistema Multiagente Autônomo de Produção de Vídeos e Documentários.
Transforma um roteiro de texto em vídeo finalizado em 1080p com narração, legendas,
busca de mídias, geração de imagens IA, edição dinâmica Ken Burns e thumbnail.
"""

__version__ = "2.0.0"
__author__ = "VideoFactoryAI Team"

from videofactory.core.context import VideoFactoryContext
from videofactory.agents.director_agent import DirectorAgent

__all__ = ["VideoFactoryContext", "DirectorAgent"]
