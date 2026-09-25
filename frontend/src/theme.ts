// Material identity colours: validated categorical palette (slots 1-6, light mode,
// on white): all adjacent-pair CVD and normal-vision checks pass. Colour follows the
// material everywhere and never its rank. Slots 3-5 sit below 3:1 contrast on white,
// so every chart carries a text legend and a table view.
import type { Category } from './api'

export const CATEGORY_ORDER: Category[] = ['metal', 'ewaste', 'paper', 'pet', 'hdpe', 'glass']

export const CATEGORY_COLOR: Record<Category, string> = {
  metal: '#2a78d6',
  ewaste: '#eb6834',
  paper: '#1baf7a',
  pet: '#eda100',
  hdpe: '#e87ba4',
  glass: '#008300',
}

export const CATEGORY_LABEL: Record<Category, string> = {
  metal: 'Metal (steel, aluminium, copper)',
  ewaste: 'E-waste',
  paper: 'Cardboard / paper',
  pet: 'PET plastic',
  hdpe: 'HDPE',
  glass: 'Glass',
}

export const CATEGORY_SHORT: Record<Category, string> = {
  metal: 'Metal',
  ewaste: 'E-waste',
  paper: 'Paper',
  pet: 'PET',
  hdpe: 'HDPE',
  glass: 'Glass',
}

export const METAL_BEARING: Category[] = ['metal', 'ewaste']

// Chart chrome
export const ACCENT = '#2a78d6' // slot 1: the single-series / emphasis hue
export const DEEMPH = '#c9c7bf' // de-emphasis grey for "the rest"
export const GRID = '#e1e0d9'
export const AXIS = '#c3c2b7'
export const MUTED = '#6f6d67'
export const NAVY = '#0b2a4a'

// Sequential blue (one hue, light -> dark) for magnitude
export const SEQ_BLUE = ['#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281']

export function seqColor(t: number): string {
  const i = Math.min(SEQ_BLUE.length - 1, Math.max(0, Math.round(t * (SEQ_BLUE.length - 1))))
  return SEQ_BLUE[i]
}
