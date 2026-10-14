<script>
export default {
  onLaunch: function () {
    console.log('App Launch')
  },
  onShow: function () {
    console.log('App Show')
  },
  onHide: function () {
    console.log('App Hide')
  },
}
</script>

<style>
	/*每个页面公共css */
	/* #ifdef H5 */
	* {
	/* #endif */
	/* #ifndef H5 */
	view, text, image, button, input {
	/* #endif */
		margin: 0;
		padding: 0;
		box-sizing: border-box;
	}

	page {
		background: linear-gradient(135deg, #ff6b6b, #ffa500);
		min-height: 100vh;
	}

	/* 全局按钮样式重置 */
	button {
		border: none;
		outline: none;
		background: none;
	}

	button::after {
		border: none;
	}
  button{transition:transform .18s ease,background-color .18s ease}
  button:active{transform:scale(.97)}
  @media (prefers-reduced-motion: reduce){view,text,button,image{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}}

	/* 全局输入框样式 */
	input {
		outline: none;
		border: none;
	}
</style>
