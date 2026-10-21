// getImageInfo reports sensor dimensions; <image> and canvas decode EXIF upright.
export function displayImageSize(info) {
  const rotated=/^(left|right)(-mirrored)?$/.test(info.orientation || '')
  return {...info,width:rotated?info.height:info.width,height:rotated?info.width:info.height}
}
