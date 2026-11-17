import unittest

from ytmpd import core


class NormalizeUrl(unittest.TestCase):
    def test_music_playlist(self):
        self.assertEqual(core.normalize_url("https://music.youtube.com/playlist?list=PL123&si=x"),
                         "https://www.youtube.com/playlist?list=PL123")

    def test_song_playing_inside_playlist(self):
        self.assertEqual(core.normalize_url("https://www.youtube.com/watch?v=abc&list=PL123&index=4"),
                         "https://www.youtube.com/playlist?list=PL123")

    def test_single_video_untouched(self):
        url = "https://www.youtube.com/watch?v=abc"
        self.assertEqual(core.normalize_url(url), url)

    def test_other_sites_untouched(self):
        url = "https://example.com/watch?list=PL123"
        self.assertEqual(core.normalize_url(url), url)


class BuildOptions(unittest.TestCase):
    def test_mp3_converts_and_tags(self):
        opts = core.build_options("out", "mp3", "320")
        keys = [pp["key"] for pp in opts["postprocessors"]]
        self.assertEqual(keys, ["FFmpegExtractAudio", "FFmpegMetadata"])
        self.assertEqual(opts["postprocessors"][0]["preferredquality"], "320")

    def test_m4a_needs_no_ffmpeg(self):
        opts = core.build_options("out", "m4a")
        self.assertEqual(opts["format"], "bestaudio[ext=m4a]")
        self.assertNotIn("postprocessors", opts)

    def test_archive_lives_in_output_folder(self):
        self.assertTrue(core.build_options("out")["download_archive"].endswith(core.ARCHIVE))
        self.assertIn("out", core.build_options("out")["download_archive"])

    def test_cookies_only_when_browser_chosen(self):
        self.assertNotIn("cookiesfrombrowser", core.build_options("out"))
        self.assertEqual(core.build_options("out", browser="firefox")["cookiesfrombrowser"], ("firefox",))

    def test_items_and_js_runtimes(self):
        opts = core.build_options("out", items="1,3-5")
        self.assertEqual(opts["playlist_items"], "1,3-5")
        self.assertIn("node", opts["js_runtimes"])

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            core.build_options("out", "flac")


class Tags(unittest.TestCase):
    def test_music_fields_win(self):
        info = {"track": "Makeba", "title": "Jain - Makeba (Official Video)", "artist": "Jain", "uploader": "JainVEVO",
                "album": "Zanaka"}
        self.assertEqual(core.tags_for(info), {"title": "Makeba", "artist": "Jain", "album": "Zanaka"})

    def test_plain_video_falls_back(self):
        info = {"title": "Me at the zoo", "uploader": "jawed"}
        self.assertEqual(core.tags_for(info), {"title": "Me at the zoo", "artist": "jawed"})


if __name__ == "__main__":
    unittest.main()
