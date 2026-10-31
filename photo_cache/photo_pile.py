"""A photographic print pile, composed locally without altering source photos."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import random

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


@dataclass(frozen=True)
class PrintPlacement:
    path: Path
    width: int
    height: int
    angle: float
    x: int
    y: int


def _intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _plan(paths, size, rng):
    width, height = size
    count = len(paths)
    # Keep a generous outer rim, including the rotated print and its shadow.
    left, top = width * .05, height * .065
    right, bottom = width-left, height-top
    inner_width, inner_height = right-left, bottom-top
    clusters = [(rng.uniform(.25, .75)*width, rng.uniform(.28, .72)*height)
                for _ in range(3)]
    weights = [rng.uniform(1.45, 1.9) if i < max(1, count*.15)
               else rng.uniform(.28, .55) if i >= count*.75
               else rng.uniform(.65, 1.15) for i in range(count)]
    rng.shuffle(weights)
    placed, boxes, focuses, covered = [], [], [], []
    for path, weight in zip(paths, weights):
        with Image.open(path) as opened:
            ratio = opened.width / opened.height
        area = inner_width * inner_height / count * weight * .95
        pw, ph = math.sqrt(area*ratio), math.sqrt(area/ratio)
        roll = rng.random()
        angle = (rng.uniform(-3, 3) if roll < .18 else
                 rng.choice((-1, 1))*rng.uniform(16, 25) if roll > .8 else
                 rng.choice((-1, 1))*rng.uniform(4, 16))
        radians = math.radians(abs(angle))
        bw = pw*math.cos(radians) + ph*math.sin(radians)
        bh = ph*math.cos(radians) + pw*math.sin(radians)
        trim = min(1, inner_width*.76/bw, inner_height*.80/bh)
        pw, ph = max(1, round(pw*trim)), max(1, round(ph*trim))
        anchor = rng.choice(clusters) if rng.random() < .65 else (
            rng.uniform(left, right), rng.uniform(top, bottom))
        target_overlap = rng.uniform(.02, .4)
        best = None
        for factor in (1, .86, .72):
            fw, fh = max(1, round(pw*factor)), max(1, round(ph*factor))
            # Include border/shadow padding in the placement bounds.
            bw = fw*math.cos(radians) + fh*math.sin(radians) + min(size)*.025
            bh = fh*math.cos(radians) + fw*math.sin(radians) + min(size)*.025
            for attempt in range(160):
                if attempt < 100:
                    cx = rng.gauss(anchor[0], inner_width*.17)
                    cy = rng.gauss(anchor[1], inner_height*.20)
                    if not (left+bw/2 <= cx <= right-bw/2 and top+bh/2 <= cy <= bottom-bh/2):
                        continue
                else:
                    cx = rng.uniform(left+bw/2, right-bw/2)
                    cy = rng.uniform(top+bh/2, bottom-bh/2)
                box = (cx-bw/2, cy-bh/2, cx+bw/2, cy+bh/2)
                overlaps = [_intersection(box, old) for old in boxes]
                overlap = sum(overlaps)/max(1,fw*fh)
                obscured = sum((_intersection(box, focus)/max(1,(focus[2]-focus[0])*(focus[3]-focus[1])))**2
                               for focus in focuses)
                buried = sum(max(0, (old_covered+extra)/max(1,(old[2]-old[0])*(old[3]-old[1]))-.48)**2
                             for old,old_covered,extra in zip(boxes,covered,overlaps))
                distance = ((cx-anchor[0])/width)**2 + ((cy-anchor[1])/height)**2
                score = (overlap-target_overlap)**2*2 + obscured*3.5 + buried*35 + distance*.65 + (1-factor)*1.1
                if best is None or score < best[0]:
                    best = (score,cx,cy,box,fw,fh)
        _,cx,cy,box,pw,ph = best
        covered = [old+_intersection(box,rect) for old,rect in zip(covered,boxes)]
        boxes.append(box)
        covered.append(0)
        focuses.append((cx-pw*.28,cy-ph*.4,cx+pw*.28,cy+ph*.22))
        placed.append(PrintPlacement(path,pw,ph,angle,round(cx),round(cy)))
    return placed


def _render_print(path, width, height, angle, border):
    # Rotate at 3x resolution, then downsample premultiplied RGBA. The
    # outer edge gets subpixel coverage without a dark transparent fringe.
    supersample = 3
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB').resize(
            (width*supersample, height*supersample), Image.Resampling.LANCZOS)
    card = ImageOps.expand(image, border*supersample, 'white').convert('RGBA')
    card = card.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    return card.convert('RGBa').resize(
        (round(card.width/supersample), round(card.height/supersample)),
        Image.Resampling.LANCZOS).convert('RGBA')


def compose_photo_pile(paths: list[Path], size: tuple[int, int], *, rng=None) -> Image.Image:
    rng = rng or random.SystemRandom()
    width, height = size
    with Image.open(rng.choice(paths)) as opened:
        background = ImageOps.fit(ImageOps.exif_transpose(opened).convert('RGB'), size,
                                  Image.Resampling.LANCZOS)
    background = ImageOps.grayscale(background).convert('RGB')
    background = ImageEnhance.Contrast(background).enhance(.55)
    background = ImageEnhance.Brightness(background).enhance(.82)
    background = background.filter(ImageFilter.GaussianBlur(max(2, min(size) / 300)))
    canvas = background.convert('RGBA')
    border = max(3, round(min(size) * .004))
    shadow_blur = max(2, round(min(size) * .0035))
    shadow_pad = shadow_blur * 4
    for placement in _plan(paths, size, rng):
        card = _render_print(placement.path, placement.width, placement.height, placement.angle, border)
        mask = Image.new('L', (card.width + shadow_pad*2, card.height + shadow_pad*2))
        mask.paste(card.getchannel('A'), (shadow_pad, shadow_pad))
        mask = mask.filter(ImageFilter.GaussianBlur(shadow_blur))
        mask = mask.point(lambda value: round(value * .38))
        shadow = Image.new('RGBA', mask.size, (0, 0, 0, 0))
        shadow.putalpha(mask)
        x = placement.x - card.width // 2
        y = placement.y - card.height // 2
        canvas.alpha_composite(shadow, (x-shadow_pad+shadow_blur, y-shadow_pad+shadow_blur*2))
        canvas.alpha_composite(card, (x, y))
    return canvas.convert('RGB')
