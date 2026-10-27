import base64
from io import BytesIO
import unittest

from fastapi import HTTPException
from PIL import Image
from meme_generator.features.upload_images import restore_upload_masks, mask_slots


def encoded(image, format):
    buffer = BytesIO()
    image.save(buffer, format)
    return buffer.getvalue()


class UploadImagesTests(unittest.TestCase):
    def setUp(self):
        self.colour = encoded(Image.new('RGB', (80, 100), (200, 120, 60)), 'JPEG')
        self.mask = Image.new('L', (80, 100))
        self.mask.putdata([i % 256 for i in range(8000)])
        self.alpha = base64.b64encode(encoded(self.mask, 'PNG')).decode()

    def test_lossless_alpha_and_unchanged_colour_dimensions(self):
        result = restore_upload_masks([self.colour], [self.alpha])[0]
        with Image.open(BytesIO(result)) as image, Image.open(BytesIO(self.colour)) as colour:
            self.assertEqual(image.size, colour.size)
            self.assertEqual(image.getchannel('A').tobytes(), self.mask.tobytes())
            self.assertEqual(image.convert('RGB').tobytes(), colour.tobytes())

    def test_legacy_and_mixed_inputs(self):
        self.assertEqual(restore_upload_masks([self.colour], []), [self.colour])
        values = restore_upload_masks([self.colour, self.colour], ['', self.alpha])
        self.assertEqual(values[0], self.colour)
        self.assertEqual(len(values), 2)

    def test_rejects_invalid_count_size_encoding_and_image_type(self):
        wrong_size = base64.b64encode(encoded(Image.new('L', (81, 100)), 'PNG')).decode()
        jpeg_mask = base64.b64encode(encoded(self.mask, 'JPEG')).decode()
        large_mask = base64.b64encode(encoded(Image.new('L', (2048, 2048)), 'PNG')).decode()
        for masks in [[self.alpha, ''], ['invalid!'], [wrong_size], [jpeg_mask], [large_mask]]:
            with self.subTest(masks_count=len(masks)), self.assertRaises(HTTPException) as caught:
                restore_upload_masks([self.colour], masks)
            self.assertEqual(caught.exception.status_code, 422)
        with self.assertRaises(HTTPException):
            restore_upload_masks([b'not an image'], [self.alpha])

    def test_concurrency_budget_released_after_failure(self):
        mask_slots.acquire(); mask_slots.acquire()
        try:
            with self.assertRaises(HTTPException) as caught:
                restore_upload_masks([self.colour], [self.alpha])
            self.assertEqual(caught.exception.status_code, 503)
        finally:
            mask_slots.release(); mask_slots.release()
        with self.assertRaises(HTTPException):
            restore_upload_masks([self.colour], ['invalid!'])
        self.assertTrue(restore_upload_masks([self.colour], [self.alpha]))
